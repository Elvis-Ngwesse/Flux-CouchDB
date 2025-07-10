import time
import random
import logging
import os
import couchdb
import requests
from faker import Faker
from faker_vehicle import VehicleProvider
from dotenv import load_dotenv
import re
import psutil
from flask import Flask
import threading
import sys

# Load environment variables
load_dotenv()

# Configuration
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASSWORD = os.getenv("COUCHDB_PASSWORD", "admin")
COUCHDB_HOST = os.getenv("COUCHDB_HOST", "couchdb")
COUCHDB_PORT = os.getenv("COUCHDB_PORT", "5984")
COUCHDB_DB = os.getenv("COUCHDB_DB", "car_prices")

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_DB = os.getenv("INFLUXDB_DB", "car_metrics")

# Logging setup
log_dir = "/app/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "generator.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger()

# --- Begin Gunicorn logging integration fix ---
try:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if gunicorn_logger.handlers:
        logger.handlers = gunicorn_logger.handlers
        logger.setLevel(gunicorn_logger.level)
    logger.propagate = True
except Exception as e:
    logger.error(f"Failed to integrate Gunicorn logging handlers: {e}")
# --- End Gunicorn logging integration fix ---

# Flask app for health check
flask_app = Flask(__name__)

@flask_app.route("/health")
def health():
    return "OK", 200

# Faker setup
fake = Faker()
fake.add_provider(VehicleProvider)

def sanitize_tag(value):
    return re.sub(r'[ ,=]', '_', str(value))

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

def connect_couchdb():
    couch = couchdb.Server(f"http://{COUCHDB_USER}:{COUCHDB_PASSWORD}@{COUCHDB_HOST}:{COUCHDB_PORT}/")
    if COUCHDB_DB not in couch:
        logger.info(f"📂 Creating CouchDB database: {COUCHDB_DB}")
        couch.create(COUCHDB_DB)
    return couch[COUCHDB_DB]

def ensure_influxdb_db_exists():
    try:
        url = f"{INFLUXDB_URL}/query"
        query = f"CREATE DATABASE {INFLUXDB_DB}"
        r = requests.post(url, params={"q": query})
        if r.status_code == 200:
            logger.info(f"🧪 Ensured InfluxDB database '{INFLUXDB_DB}' exists.")
        else:
            logger.warning(f"⚠️ Failed to create InfluxDB DB: {r.status_code}, {r.text}")
    except Exception as e:
        logger.error(f"❌ InfluxDB check failed: {e}")

def push_metric(measurement, fields, tags=None, max_retries=5, base_delay=1):
    line = measurement

    if tags:
        tag_str = ",".join(f"{sanitize_tag(k)}={sanitize_tag(v)}" for k, v in tags.items())
        line += f",{tag_str}"

    field_str = ",".join(f"{k}={format_field_value(v)}" for k, v in fields.items())
    line += f" {field_str}"

    url = f"{INFLUXDB_URL}/write?db={INFLUXDB_DB}&precision=ns"
    headers = {"Content-Type": "text/plain"}

    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(url, headers=headers, data=line, timeout=5)
            if r.status_code == 204:
                logger.info(f"✅ Metric pushed to InfluxDB: {line}")
                return True
            else:
                logger.warning(f"⚠️ Attempt {attempt}: InfluxDB push failed ({r.status_code}) - {r.text}")
        except requests.RequestException as e:
            logger.error(f"❌ Attempt {attempt}: Exception pushing to InfluxDB - {e}")

        if attempt < max_retries:
            delay = base_delay * (2 ** (attempt - 1))
            logger.info(f"⏳ Retrying in {delay:.1f} seconds...")
            time.sleep(delay)

    logger.error("❌ Max retries reached. Failed to push metrics.")
    return False

def generate_and_insert_cars(db, num_cars=200):
    logger.info(f"🔧 Generating {num_cars} fake car records...")
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
            if inserted % 50 == 0:
                logger.info(f"📦 Inserted {inserted} records...")
        except Exception as e:
            logger.error(f"❌ Insert failed at #{i + 1}: {e}")

    logger.info(f"✅ Finished inserting {inserted} records.")

    if inserted == 0:
        logger.warning("⚠️ No data inserted. Skipping metrics.")
        return

    avg_price = sum(prices) / inserted
    logger.info(f"📊 Average price: £{avg_price:,.2f}")
    logger.info("📤 Pushing metrics to InfluxDB...")

    push_metric(
        measurement="car_data_generator",
        fields={
            "inserted_records": inserted,
            "average_price": avg_price
        },
        tags={"source": "generator"}
    )

def report_system_metrics():
    logger.info("🖥️ Reporting system metrics to InfluxDB...")
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        push_metric(
            measurement="car_generator_system",
            fields={
                "cpu_percent": cpu,
                "mem_used_mb": int(mem.used / 1024 / 1024),
                "mem_available_mb": int(mem.available / 1024 / 1024),
                "mem_percent": mem.percent
            },
            tags={"host": os.uname()[1]}
        )
    except Exception as e:
        logger.error(f"❌ Failed to collect/report system metrics: {e}")

def main():
    logger.info("🚀 Car Data Generator starting...")
    logger.info(f"🗃️ CouchDB → {COUCHDB_HOST}:{COUCHDB_PORT}, DB: {COUCHDB_DB}")
    logger.info(f"📡 InfluxDB → {INFLUXDB_URL}, DB: {INFLUXDB_DB}")
    logger.info(f"🕐 Startup time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    ensure_influxdb_db_exists()

    while True:
        try:
            logger.info("🔄 New data generation cycle...")
            db = connect_couchdb()
            generate_and_insert_cars(db, 200)
            report_system_metrics()
            logger.info("⏳ Sleeping for 2 minutes...\n")
            time.sleep(120)
        except Exception as e:
            logger.error(f"💥 Main loop error: {e}")
            time.sleep(60)

# Start the background worker when module is loaded (e.g. via Gunicorn)
def start_background_worker():
    t = threading.Thread(target=main, daemon=True)
    t.start()

start_background_worker()

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=8060)
