import json
import logging
import os

import ee
from dotenv import load_dotenv

# Only load .env in development (when GEE_PRIVATE_KEY is not already injected)
_gee_private_key_raw = os.getenv("GEE_PRIVATE_KEY")
if not _gee_private_key_raw:
    load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authentication
#
#   Production  → GEE_PRIVATE_KEY   : service-account JSON passed as a string
#   Development → GEE_PRIVATE_KEY_PATH : path to the JSON key file
#
#   Both modes also require:
#     GEE_PROJECT_ID      — GEE cloud project ID
#     GEE_SERVICE_ACCOUNT — service account e-mail
# ---------------------------------------------------------------------------
_project  = os.getenv("GEE_PROJECT_ID")
_sa_email = os.getenv("GEE_SERVICE_ACCOUNT")

if not _project:
    raise EnvironmentError("GEE_PROJECT_ID environment variable is not set.")
if not _sa_email:
    raise EnvironmentError("GEE_SERVICE_ACCOUNT environment variable is not set.")

_gee_private_key_raw = os.getenv("GEE_PRIVATE_KEY")

if _gee_private_key_raw:
    # --- Production: key material injected directly as a JSON string ---
    logger.info("GEE auth: using GEE_PRIVATE_KEY (production mode)")
    try:
        json.loads(_gee_private_key_raw)  # validate JSON before passing
    except json.JSONDecodeError as exc:
        raise EnvironmentError(
            "GEE_PRIVATE_KEY is set but is not valid JSON."
        ) from exc
    # ee.ServiceAccountCredentials expects a raw JSON string, not a dict
    _credentials = ee.ServiceAccountCredentials(_sa_email, key_data=_gee_private_key_raw)

else:
    # --- Development: key file loaded from disk ---
    _key_path = os.getenv("GEE_PRIVATE_KEY_PATH")
    if not _key_path:
        raise EnvironmentError(
            "Neither GEE_PRIVATE_KEY nor GEE_PRIVATE_KEY_PATH is set."
        )

    # Resolve relative paths from the repo root (one level above this file)
    if not os.path.isabs(_key_path):
        _key_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", _key_path)
        )

    if not os.path.exists(_key_path):
        raise FileNotFoundError(
            f"GEE key file not found at resolved path: {_key_path}"
        )

    logger.info("GEE auth: using key file at %s (development mode)", _key_path)
    _credentials = ee.ServiceAccountCredentials(_sa_email, key_file=_key_path)

ee.Initialize(credentials=_credentials, project=_project)
logger.info("Google Earth Engine initialised (project=%s)", _project)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_best_image(area: ee.Geometry, start_date: str, end_date: str) -> ee.Image:
    """Return the median of cloud-filtered Sentinel-2 SR images for the AOI."""
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(area)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
    )

    count = collection.size().getInfo()
    if count == 0:
        raise ValueError(
            f"No Sentinel-2 images found between {start_date} and {end_date}."
        )

    return collection.median()


def calculate_ndvi(image: ee.Image) -> ee.Image:
    return image.normalizedDifference(["B8", "B4"]).rename("NDVI")


def calculate_ndbi(image: ee.Image) -> ee.Image:
    return image.normalizedDifference(["B11", "B8"]).rename("NDBI")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyze_area(
    lat, lon, radius, d1_start, d1_end, d2_start, d2_end, polygon=None
) -> dict:
    # ------------------------------------------------------------------
    # 1. Build AOI geometry
    # ------------------------------------------------------------------
    if polygon is not None:
        if polygon.get("type") != "Polygon":
            raise ValueError("Only GeoJSON Polygon type is supported.")
        area = ee.Geometry.Polygon(polygon["coordinates"])
    elif lat is not None and lon is not None:
        area = ee.Geometry.Point([lon, lat]).buffer(radius)
    else:
        raise ValueError("Either polygon or lat/lon must be provided.")

    # Padded bounding box used for thumbnail exports
    buffered_bounds = area.bounds().buffer(500).bounds()

    # ------------------------------------------------------------------
    # 2. Fetch images
    # ------------------------------------------------------------------
    image1 = get_best_image(area, d1_start, d1_end)
    image2 = get_best_image(area, d2_start, d2_end)

    # ------------------------------------------------------------------
    # 3. Spectral indices
    # ------------------------------------------------------------------
    ndvi1 = calculate_ndvi(image1)
    ndvi2 = calculate_ndvi(image2)
    ndbi1 = calculate_ndbi(image1)
    ndbi2 = calculate_ndbi(image2)

    ndvi_change = ndvi2.subtract(ndvi1)
    ndbi_change = ndbi2.subtract(ndbi1)

    # ------------------------------------------------------------------
    # 4. Change masks
    # ------------------------------------------------------------------
    veg_loss      = ndvi_change.lt(-0.2)
    builtup_gain  = ndbi_change.gt(0.2)
    encroachment_mask = veg_loss.And(builtup_gain)

    veg_loss     = veg_loss.updateMask(veg_loss).clip(area)
    builtup_gain = builtup_gain.updateMask(builtup_gain).clip(area)
    encroachment = encroachment_mask.updateMask(encroachment_mask).clip(area)

    # ------------------------------------------------------------------
    # 5. Area statistics
    # ------------------------------------------------------------------
    pixel_area = ee.Image.pixelArea()

    total_area = pixel_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=area,
        scale=10,
        maxPixels=1e10,
    ).getInfo()["area"]

    encroach_area = pixel_area.updateMask(encroachment).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=area,
        scale=10,
        maxPixels=1e10,
    ).getInfo()["area"]

    percent = (encroach_area / total_area) * 100 if total_area else 0

    if percent < 5:
        risk = "Low"
    elif percent < 20:
        risk = "Medium"
    else:
        risk = "High"

    # ------------------------------------------------------------------
    # 6. Tile layer URLs
    # ------------------------------------------------------------------
    veg_loss_tile = veg_loss.getMapId(
        {"min": 0, "max": 1, "palette": ["red"]}
    )["tile_fetcher"].url_format

    builtup_tile = builtup_gain.getMapId(
        {"min": 0, "max": 1, "palette": ["purple"]}
    )["tile_fetcher"].url_format

    encroach_tile = encroachment.getMapId(
        {"min": 0, "max": 1, "palette": ["orange"]}
    )["tile_fetcher"].url_format

    # ------------------------------------------------------------------
    # 7. Thumbnail composites
    # ------------------------------------------------------------------
    rgb_vis = {"min": 0, "max": 3000}

    aoi_outline = ee.Image().byte().paint(
        ee.FeatureCollection([ee.Feature(buffered_bounds)]), 1, 3
    )

    t0_vis  = image1.select(["B4", "B3", "B2"]).visualize(**rgb_vis)
    t1_vis  = image2.select(["B4", "B3", "B2"]).visualize(**rgb_vis)
    enc_overlay = encroachment.visualize(min=0, max=1, palette=["orange"])
    outline_vis = aoi_outline.visualize(palette=["yellow"])

    t0_composite  = t0_vis.blend(outline_vis)
    t1_composite  = t1_vis.blend(outline_vis)
    enc_composite = t1_vis.blend(enc_overlay).blend(outline_vis)

    thumb_params = {"dimensions": 1024, "region": buffered_bounds, "format": "png"}
    t0_thumb      = t0_composite.getThumbURL(thumb_params)
    t1_thumb      = t1_composite.getThumbURL(thumb_params)
    encroach_thumb = enc_composite.getThumbURL(thumb_params)

    # ------------------------------------------------------------------
    # 8. Return serialisable result dict
    # ------------------------------------------------------------------
    return {
        "encroachment_percent":   round(percent, 2),
        "risk_level":             risk,
        "vegetation_loss_tile":   veg_loss_tile,
        "builtup_increase_tile":  builtup_tile,
        "encroachment_tile":      encroach_tile,
        "t0_thumb":               t0_thumb,
        "t1_thumb":               t1_thumb,
        "encroach_thumb":         encroach_thumb,
    }
