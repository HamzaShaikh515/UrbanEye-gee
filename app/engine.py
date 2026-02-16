import ee

ee.Initialize(project="urbaneye-477115")

def get_best_image(area, start_date, end_date):

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(area)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 40))  # increase threshold
    )

    count = collection.size().getInfo()

    if count == 0:
        raise ValueError(f"No Sentinel-2 images found between {start_date} and {end_date}")

    return collection.median()



def calculate_ndvi(image):
    return image.normalizedDifference(['B8', 'B4']).rename('NDVI')


def calculate_ndbi(image):
    return image.normalizedDifference(['B11', 'B8']).rename('NDBI')


def analyze_area(lat, lon, radius, d1_start, d1_end, d2_start, d2_end, polygon=None):

    # ----------------------------
    # 1️⃣ Create AOI Geometry
    # ----------------------------
    if polygon is not None:
        if polygon.get("type") != "Polygon":
            raise ValueError("Only Polygon type is supported")

        coords = polygon["coordinates"]
        area = ee.Geometry.Polygon(coords)
    else:
        point = ee.Geometry.Point([lon, lat])
        area = point.buffer(radius)

    # ----------------------------
    # 2️⃣ Get Images
    # ----------------------------
    image1 = get_best_image(area, d1_start, d1_end)
    image2 = get_best_image(area, d2_start, d2_end)

    # ----------------------------
    # 3️⃣ Calculate Indices
    # ----------------------------
    ndvi1 = calculate_ndvi(image1)
    ndvi2 = calculate_ndvi(image2)

    ndbi1 = calculate_ndbi(image1)
    ndbi2 = calculate_ndbi(image2)

    ndvi_change = ndvi2.subtract(ndvi1)
    ndbi_change = ndbi2.subtract(ndbi1)

    # ----------------------------
    # 4️⃣ Create Masks
    # ----------------------------
    veg_loss = ndvi_change.lt(-0.2)
    builtup_gain = ndbi_change.gt(0.2)

    encroachment_mask = veg_loss.And(builtup_gain)

    # 🔥 IMPORTANT: Mask + Clip
    veg_loss = veg_loss.updateMask(veg_loss).clip(area)
    builtup_gain = builtup_gain.updateMask(builtup_gain).clip(area)
    encroachment = encroachment_mask.updateMask(encroachment_mask).clip(area)

    # ----------------------------
    # 5️⃣ Area Calculation
    # ----------------------------
    pixel_area = ee.Image.pixelArea()

    total_area = pixel_area.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=area,
        scale=10,
        maxPixels=1e10
    ).getInfo()['area']

    encroach_area = pixel_area.updateMask(encroachment).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=area,
        scale=10,
        maxPixels=1e10
    ).getInfo()['area']

    percent = (encroach_area / total_area) * 100 if total_area else 0

    if percent < 5:
        risk = "Low"
    elif percent < 20:
        risk = "Medium"
    else:
        risk = "High"

    # ----------------------------
    # 6️⃣ Generate Tile Layers
    # ----------------------------
    veg_loss_tile = veg_loss.getMapId(
        {
            'min': 0,
            'max': 1,
            'palette': ['red']
        }
    )['tile_fetcher'].url_format

    builtup_tile = builtup_gain.getMapId(
        {
            'min': 0,
            'max': 1,
            'palette': ['purple']
        }
    )['tile_fetcher'].url_format

    encroach_tile = encroachment.getMapId(
        {
            'min': 0,
            'max': 1,
            'palette': ['orange']
        }
    )['tile_fetcher'].url_format

    # True color images
    true_color1 = image1.select(['B4', 'B3', 'B2']).clip(area)
    true_color2 = image2.select(['B4', 'B3', 'B2']).clip(area)

    t0_thumb = get_thumbnail(true_color1, area)
    t1_thumb = get_thumbnail(true_color2, area)
    encroach_thumb = get_thumbnail(encroachment, area, palette=['orange'])


    return {
        "encroachment_percent": round(percent, 2),
        "risk_level": risk,
        "vegetation_loss_tile": veg_loss_tile,
        "builtup_increase_tile": builtup_tile,
        "encroachment_tile": encroach_tile,
        "t0_thumb": t0_thumb,
        "t1_thumb": t1_thumb,
        "encroach_thumb": encroach_thumb
    }

def get_thumbnail(image, area, palette=None):
    vis_params = {
        'min': 0,
        'max': 3000,
        'dimensions': 512,
        'region': area
    }

    if palette:
        vis_params.update({
            'min': 0,
            'max': 1,
            'palette': palette
        })

    url = image.getThumbURL(vis_params)
    return url
