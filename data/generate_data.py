import time
import couchdb
from faker import Faker
from faker_vehicle import VehicleProvider
import os
from dotenv import load_dotenv
import logging
import random
import requests
import re

# Load environment variables from .env file
load_dotenv()

# Ensure log directory exists
log_dir = "/app/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()  # Also logs to stdout for Kubernetes logging
        ]
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

# InfluxDB configuration for 1.x
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_DB = os.getenv("INFLUXDB_DB", "car_metrics")

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
        # Escape backslash and double quotes for InfluxDB
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return f"{value}i"
    else:
        return str(value)


def sanitize_tag_value(value):
    # Remove spaces, commas, equal signs (InfluxDB tags cannot have these)
    return re.sub(r'[ ,=]', '_', str(value))


def push_metric(measurement, fields, tags=None, timestamp=None,
                max_retries=5, base_delay=1):
    """
    Push a metric line to InfluxDB with retries and error handling.

    Args:
      measurement (str): Measurement name.
      fields (dict): Field key-values.
      tags (dict): Tag key-values.
      timestamp (int or str): Optional timestamp in ns.
      max_retries (int): Max retry attempts.
      base_delay (int or float): Initial delay in seconds for retry backoff.
    """
    line = measurement
    if tags:
        tag_str = ",".join(f"{k}={sanitize_tag_value(v)}" for k, v in tags.items())
        line += f",{tag_str}"
    field_str = ",".join(f"{k}={format_field_value(v)}" for k, v in fields.items())
    line += f" {field_str}"
    if timestamp:
        line += f" {timestamp}"

    url = f"{INFLUXDB_URL}/write?db={INFLUXDB_DB}&precision=ns"
    headers = {"Content-Type": "text/plain; charset=utf-8"}

    attempt = 0
    while attempt <= max_retries:
        try:
            resp = requests.post(url, headers=headers, data=line, timeout=5)
            if resp.status_code == 204:
                logger.debug(f"Metric pushed successfully on attempt {attempt + 1}: {line}")
                return True
            else:
                logger.warning(f"Attempt {attempt + 1} - InfluxDB push failed with status {resp.status_code}: {resp.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Attempt {attempt + 1} - Exception pushing metric: {e}")

        attempt += 1
        if attempt <= max_retries:
            delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
            logger.info(f"Retrying in {delay:.1f} seconds...")
            time.sleep(delay)
        else:
            logger.error(f"Max retries ({max_retries}) reached. Failed to push metric: {line}")

    return False


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
        price = random.randint(2000, 45000)
        doc = {
            "country": fake.country(),
            "car_type": fake.vehicle_make_model(),
            "price": price,
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
