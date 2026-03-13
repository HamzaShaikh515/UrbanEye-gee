import ee
import os
from dotenv import load_dotenv

load_dotenv()

service_account = os.getenv("GEE_SERVICE_ACCOUNT")
key_file = os.getenv('GEE_PRIVATE_KEY_PATH')
project_id = os.getenv("GEE_PROJECT_ID")

credentials = ee.ServiceAccountCredentials(service_account, key_file)
ee.Initialize(credentials, project=project_id)

collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
    .filterDate("2022-01-01", "2022-01-05") \
    .limit(1)

image = collection.first()

print(image.getInfo())