🌍 UrbanEye Backend

2️⃣ Create Virtual Environment
python -m venv .venv

Activate:

Windows (PowerShell)
.venv\Scripts\activate

macOS/Linux
source .venv/bin/activate

3️⃣ Install Dependencies
pip install -r requirements.txt


If requirements.txt not present:

pip install fastapi uvicorn earthengine-api sqlalchemy psycopg2-binary geoalchemy2 shapely python-dotenv

4️⃣ Setup Google Earth Engine

Authenticate once:

earthengine authenticate


Follow browser login process.

5️⃣ Setup PostGIS Using Docker

Run:

docker run --name urbaneye-postgis \
  -e POSTGRES_USER=urbaneye \
  -e POSTGRES_PASSWORD=urbaneye123 \
  -e POSTGRES_DB=urbaneye_db \
  -p 5432:5432 \
  -d postgis/postgis


Verify container:

docker ps

6️⃣ Configure Database Connection

In app/database.py:

DATABASE_URL = "postgresql://urbaneye:urbaneye123@localhost:5432/urbaneye_db"

7️⃣ Create Database Tables

Run once:

python run_once.py

8️⃣ Start Backend Server
uvicorn app.main:app --reload


Backend will run at:

http://127.0.0.1:8000


Swagger docs:

http://127.0.0.1:8000/docs