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
import psutil
import threading

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
        logging.StreamHandler()
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
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return f"{value}i"
    else:
        return str(value)


def sanitize_tag_value(value):
    return re.sub(r'[ ,=]', '_', str(value))


def push_metric(measurement, fields, tags=None, timestamp=None, max_retries=5, base_delay=1):
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

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=line, timeout=5)
            if resp.status_code == 204:
                logger.debug(f"Metric pushed successfully: {line}")
                return True
            else:
                logger.warning(f"Attempt {attempt + 1} - InfluxDB push failed: {resp.status_code} {resp.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Attempt {attempt + 1} - Exception pushing metric: {e}")

        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            logger.info(f"Retrying in {delay:.1f}s...")
            time.sleep(delay)
        else:
            logger.error(f"Max retries reached. Failed to push: {line}")
    return False


def push_resource_metrics():
    try:
        process = psutil.Process(os.getpid())
        cpu = process.cpu_percent(interval=1)
        mem = process.memory_info().rss / (1024 * 1024)  # in MB
        push_metric(
            measurement="resource_usage",
            fields={
                "cpu_percent": cpu,
                "memory_mb": mem
            },
            tags={
                "app": "car-data-generator"
            }
        )
    except Exception as e:
        logger.error(f"Error pushing resource metrics: {e}")


def start_metrics_loop():
    def loop():
        while True:
            push_resource_metrics()
            time.sleep(60)

    t = threading.Thread(target=loop, daemon=True)
    t.start()


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

    # Push summary to InfluxDB
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
    start_metrics_loop()
    while True:
        db = connect_couchdb()
        generate_and_insert_cars(db, 200)
        logger.info("Sleeping for 2 minutes...")
        time.sleep(120)


if __name__ == "__main__":
    main()
