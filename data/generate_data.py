import time
import couchdb
from faker import Faker
from faker_vehicle import VehicleProvider
import os
from dotenv import load_dotenv
import logging
import random
import requests

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger()

# Setup Faker and add vehicle provider
fake = Faker()
fake.add_provider(VehicleProvider)

# CouchDB configuration
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")
couchdb_url = f"http://{user}:{password}@{host}:{port}/"
db_name = "car_prices"

# InfluxDB configuration
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "car_metrics")
INFLUXDB_DB = INFLUXDB_BUCKET  # fallback for compatibility with v1.8

max_retries = 10
retry_delay = 3  # seconds

def ensure_influxdb_db_exists():
    logger.info(f"Ensuring InfluxDB DB '{INFLUXDB_DB}' exists...")
    try:
        url = f"{INFLUXDB_URL}/query"
        params = {"q": f"CREATE DATABASE {INFLUXDB_DB}"}
        r = requests.post(url, params=params)
        if r.status_code == 200:
            logger.info("✅ InfluxDB DB ensured.")
        else:
            logger.warning(f"⚠️ Could not ensure InfluxDB DB: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"❌ Error ensuring InfluxDB DB: {e}")

def format_field_value(value):
    if isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return f"{value}i"
    else:
        return str(value)

def push_metric(measurement, fields, tags=None, timestamp=None):
    line = measurement
    if tags:
        tag_str = ",".join(f"{k}={v}" for k, v in tags.items())
        line += f",{tag_str}"
    field_str = ",".join(f"{k}={format_field_value(v)}" for k, v in fields.items())
    line += f" {field_str}"
    if timestamp:
        line += f" {timestamp}"

    # Supports token or no-token mode
    if INFLUXDB_TOKEN:
        url = f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=ns"
        headers = {
            "Authorization": f"Token {INFLUXDB_TOKEN}",
            "Content-Type": "text/plain; charset=utf-8"
        }
    else:
        url = f"{INFLUXDB_URL}/write?db={INFLUXDB_DB}&precision=ns"
        headers = {"Content-Type": "text/plain; charset=utf-8"}

    try:
        resp = requests.post(url, headers=headers, data=line)
        if resp.status_code != 204:
            logger.warning(f"InfluxDB push failed: {resp.status_code} {resp.text}")
        else:
            logger.debug(f"Metric pushed: {line}")
    except Exception as e:
        logger.error(f"Error pushing metric to InfluxDB: {e}")

def connect_couchdb():
    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to CouchDB ({attempt + 1}/{max_retries})...")
            couch = couchdb.Server(couchdb_url)
            if db_name in couch:
                db = couch[db_name]
                logger.info(f"Connected to CouchDB database '{db_name}'")
            else:
                db = couch.create(db_name)
                logger.info(f"Created CouchDB database '{db_name}'")
            return db
        except Exception as e:
            logger.warning(f"Connection failed: {e}")
            time.sleep(retry_delay)
    logger.error("❌ Could not connect to CouchDB.")
    raise SystemExit("Failed to connect to CouchDB")

def generate_and_insert_cars(db, num_cars=200):
    logger.info(f"Generating {num_cars} fake car records...")
    inserted = 0
    prices = []

    for i in range(num_cars):
        doc = {
            "country": fake.country(),
            "car_type": fake.vehicle_make_model(),
            "price": price := random.randint(2000, 45000),
            "mileage": random.randint(10000, 200000),
            "year": random.randint(2005, 2024),
            "location": fake.city()
        }
        try:
            db.save(doc)
            prices.append(price)
            inserted += 1
        except Exception as e:
            logger.error(f"Insert failed for record #{i + 1}: {e}")

    logger.info(f"✅ Inserted {inserted}/{num_cars} records")

    # Push metrics to InfluxDB
    avg_price = sum(prices) / inserted if inserted else 0
    push_metric(
        measurement="car_data_generator",
        fields={
            "inserted_records": inserted,
            "average_price": avg_price
        },
        tags={"source": "car_data_generator"}
    )

def main():
    logger.info("🚀 Starting car data generator...")
    ensure_influxdb_db_exists()
    while True:
        db = connect_couchdb()
        generate_and_insert_cars(db, 200)
        logger.info("Sleeping for 2 minutes...")
        time.sleep(120)

if __name__ == "__main__":
    main()
