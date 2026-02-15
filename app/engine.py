import ee

ee.Initialize(project="urbaneye-477115")

def get_best_image(area, start, end):
    collection = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(area)
        .filterDate(start, end)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 5))
        .sort('CLOUDY_PIXEL_PERCENTAGE')
    )
    return collection.first().clip(area)


def calculate_ndvi(image):
    return image.normalizedDifference(['B8', 'B4']).rename('NDVI')


def calculate_ndbi(image):
    return image.normalizedDifference(['B11', 'B8']).rename('NDBI')


def analyze_area(lat, lon, radius, d1_start, d1_end, d2_start, d2_end, polygon=None):

    if polygon is not None:
        # Only support GeoJSON Polygons
        if polygon.get("type") != "Polygon":
            raise ValueError("Only Polygon type is supported")

        coords = polygon["coordinates"]
        # Build Earth Engine Geometry Polygon
        area = ee.Geometry.Polygon(coords)
    else:
        point = ee.Geometry.Point([lon, lat])
        area = point.buffer(radius)

    image1 = get_best_image(area, d1_start, d1_end)
    image2 = get_best_image(area, d2_start, d2_end)

    ndvi1 = calculate_ndvi(image1)
    ndvi2 = calculate_ndvi(image2)

    ndbi1 = calculate_ndbi(image1)
    ndbi2 = calculate_ndbi(image2)

    ndvi_change = ndvi2.subtract(ndvi1)
    ndbi_change = ndbi2.subtract(ndbi1)

    veg_loss = ndvi_change.lt(-0.2)
    builtup_gain = ndbi_change.gt(0.2)

    encroachment = veg_loss.And(builtup_gain)

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

    percent = (encroach_area / total_area) * 100

    if percent < 5:
        risk = "Low"
    elif percent < 20:
        risk = "Medium"
    else:
        risk = "High"

    # Generate Tile Layers
    veg_loss_tile = veg_loss.selfMask().getMapId(
        {'palette': ['red']}
    )['tile_fetcher'].url_format

    builtup_tile = builtup_gain.selfMask().getMapId(
        {'palette': ['purple']}
    )['tile_fetcher'].url_format

    encroach_tile = encroachment.selfMask().getMapId(
        {'palette': ['orange']}
    )['tile_fetcher'].url_format

    return {
        "encroachment_percent": round(percent, 2),
        "risk_level": risk,
        "vegetation_loss_tile": veg_loss_tile,
        "builtup_increase_tile": builtup_tile,
        "encroachment_tile": encroach_tile
    }
