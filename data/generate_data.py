import time
import couchdb
from faker import Faker
from faker_vehicle import VehicleProvider
import os
from dotenv import load_dotenv
import logging
import random

# Load environment variables from .env file
load_dotenv()

# Setup logging to console only (stdout)
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG to capture all logs; change to INFO to reduce verbosity
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # log to container stdout for Kibana/ELK
)
logger = logging.getLogger()

# Setup Faker and add vehicle provider
fake = Faker()
fake.add_provider(VehicleProvider)

# CouchDB connection parameters
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")

couchdb_url = f"http://{user}:{password}@{host}:{port}/"
db_name = "car_prices"

max_retries = 10
retry_delay = 3  # seconds

def connect_couchdb():
    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to connect to CouchDB (try {attempt + 1}/{max_retries}) at {couchdb_url}")
            couch = couchdb.Server(couchdb_url)
            if db_name in couch:
                db = couch[db_name]
                logger.info(f"Database '{db_name}' exists, connected successfully.")
            else:
                db = couch.create(db_name)
                logger.info(f"Database '{db_name}' created and connected successfully.")
            return db
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: Could not connect to CouchDB - {e}")
            time.sleep(retry_delay)
    logger.error("Failed to connect to CouchDB after several retries. Exiting.")
    raise SystemExit("Cannot connect to CouchDB")

def generate_and_insert_cars(db, num_cars=200):
    logger.info(f"Generating and inserting {num_cars} fake car records into CouchDB")
    inserted = 0
    for i in range(num_cars):
        doc = {
            "country": fake.country(),
            "car_type": fake.vehicle_make_model(),
            "price": random.randint(2000, 45000),
            "mileage": random.randint(10000, 200000),
            "year": random.randint(2005, 2024),
            "location": fake.city()
        }
        try:
            db.save(doc)
            inserted += 1
            logger.debug(f"Inserted doc #{i+1}: {doc}")
        except Exception as e:
            logger.error(f"Failed to save document #{i+1}: {e}")
    logger.info(f"✅ Inserted {inserted}/{num_cars} fake car records successfully.")

def main():
    logger.info("Starting fake car data generator script")
    while True:
        db = connect_couchdb()
        generate_and_insert_cars(db, 200)
        logger.info("Sleeping for 2 minutes before next batch insertion...")
        time.sleep(120)  # wait 2 minutes before next run

if __name__ == "__main__":
    main()
