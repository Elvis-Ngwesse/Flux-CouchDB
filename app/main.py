import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import couchdb
import logging
import os
import pandas as pd
from dotenv import load_dotenv
import time
import random
import requests
import re
import psutil
from flask import Flask
from threading import Thread
from functools import lru_cache

# Load .env vars
load_dotenv()

# Setup logging
log_dir = "/app/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    force=True
)
logger = logging.getLogger(__name__)

# CouchDB config
COUCHDB_USER = os.getenv("COUCHDB_USER", "admin")
COUCHDB_PASS = os.getenv("COUCHDB_PASSWORD", "admin")
COUCHDB_HOST = os.getenv("COUCHDB_HOST", "couchdb")
COUCHDB_PORT = os.getenv("COUCHDB_PORT", "5984")
COUCHDB_URL = f"http://{COUCHDB_USER}:{COUCHDB_PASS}@{COUCHDB_HOST}:{COUCHDB_PORT}/"
DB_NAME = "car_prices"

# InfluxDB config
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_DB = os.getenv("INFLUXDB_DB", "car_metrics")

# Connect to CouchDB
couch = None
for attempt in range(10):
    try:
        logger.info(f"Connecting to CouchDB (attempt {attempt+1})...")
        couch = couchdb.Server(COUCHDB_URL)
        db = couch[DB_NAME] if DB_NAME in couch else couch.create(DB_NAME)
        logger.info("✅ Connected to CouchDB.")
        break
    except Exception as e:
        logger.warning(f"❌ CouchDB error: {e}")
        time.sleep(3)
else:
    raise SystemExit("❌ Could not connect to CouchDB")

# Ensure CouchDB mango index
def ensure_indexes():
    try:
        db.index_field(["country"])
        logger.info("✅ CouchDB index on 'country' created")
    except Exception as e:
        logger.error(f"❌ Failed to create index: {e}")
ensure_indexes()

# Ensure InfluxDB database exists
def ensure_influxdb_db_exists():
    try:
        url = f"{INFLUXDB_URL}/query"
        r = requests.post(url, params={"q": f"CREATE DATABASE {INFLUXDB_DB}"})
        if r.status_code == 200:
            logger.info(f"✅ InfluxDB DB '{INFLUXDB_DB}' ensured.")
        else:
            logger.warning(f"⚠️ InfluxDB ensure failed: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"❌ InfluxDB check failed: {e}")
ensure_influxdb_db_exists()

# Helper functions for metrics
def format_field_value(val):
    if isinstance(val, str): return f'"{val.replace("\\", "\\\\").replace("\"", "\\\"")}"'
    if isinstance(val, bool): return "true" if val else "false"
    if isinstance(val, int): return f"{val}i"
    return str(val)

def sanitize_tag_value(val): return re.sub(r"[ ,=]", "_", val)

def push_metric(measurement, fields, tags=None, timestamp=None, retries=5, delay=1):
    line = measurement
    if tags:
        tag_str = ",".join(f"{k}={sanitize_tag_value(str(v))}" for k, v in tags.items())
        line += f",{tag_str}"
    field_str = ",".join(f"{k}={format_field_value(v)}" for k, v in fields.items())
    line += f" {field_str}"
    if timestamp:
        line += f" {timestamp}"

    url = f"{INFLUXDB_URL}/write?db={INFLUXDB_DB}&precision=ns"
    headers = {"Content-Type": "text/plain"}

    for attempt in range(1, retries+1):
        try:
            r = requests.post(url, headers=headers, data=line, timeout=5)
            if r.status_code == 204:
                logger.info(f"✅ Metric pushed: {line}")
                return True
            else:
                logger.warning(f"❌ Metric push failed {r.status_code}: {r.text}")
        except Exception as e:
            logger.error(f"🚨 Metric push error: {e}")
        time.sleep(delay * 2 ** (attempt - 1))
    logger.error("❌ Max retries reached.")
    return False

def async_push_metric(*args, **kwargs):
    Thread(target=push_metric, args=args, kwargs=kwargs, daemon=True).start()

# Caching
@lru_cache(maxsize=20)
def get_country_data(country):
    logger.info(f"🔁 Fetching fresh data for {country}")
    return tuple(db.find({"selector": {"country": country}}))  # must be hashable

def clear_country_cache():
    get_country_data.cache_clear()
    logger.info("🧹 Cleared cached country data")

# UI Setup
CAR_IMAGES = [
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/car-49278_1280.jpg",
    "https://cdn.pixabay.com/photo/2015/01/19/13/51/car-604019_1280.jpg",
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/auto-49277_1280.jpg",
]

def get_countries():
    countries = set()
    for doc in db.find({"selector": {}, "fields": ["country"]}):
        countries.add(doc.get('country', 'Unknown'))
    return sorted(list(countries))

countries_list = get_countries()

flask_server = Flask(__name__)
@flask_server.route("/health")
def health(): return "OK", 200

app = dash.Dash(__name__, server=flask_server)
server = app.server  # Expose Flask server for Gunicorn

app.layout = html.Div([
    html.H1("🚗 Used Car Market Dashboard (£)", style={"textAlign": "center"}),
    html.Img(id="car-image", src=random.choice(CAR_IMAGES),
             style={"width": "100%", "maxHeight": "300px", "objectFit": "cover"}),
    dcc.Dropdown(
        id='country-dropdown',
        options=[{"label": c, "value": c} for c in countries_list],
        value=countries_list[0] if countries_list else None,
        placeholder="Select a country",
        style={"marginBottom": "10px"}
    ),
    dcc.Interval(id='interval', interval=120000, n_intervals=0),
    dcc.Interval(id='image-interval', interval=60000, n_intervals=0),
    dcc.Interval(id='clear-cache-interval', interval=120000, n_intervals=0),
    dcc.Graph(id='price-bar'),
    dcc.Graph(id='price-line'),
    dcc.Graph(id='car-pie')
])

@app.callback(
    [Output('price-bar', 'figure'),
     Output('price-line', 'figure'),
     Output('car-pie', 'figure')],
    [Input('country-dropdown', 'value'),
     Input('interval', 'n_intervals')]
)
def update_graphs(country, _):
    if not country:
        return [{"data": [], "layout": {"title": "Select a country"}}] * 3
    try:
        cars = list(get_country_data(country))
        df = pd.DataFrame(cars)
        if df.empty:
            return [{"data": [], "layout": {"title": "No data"}}] * 3
    except Exception as e:
        logger.error(f"❌ Data fetch error: {e}")
        return [{"data": [], "layout": {"title": "Error"}}] * 3

    # Graphs
    bar = {
        "data": [{"x": df["car_type"], "y": df["price"], "type": "bar"}],
        "layout": {"title": f"Prices in {country}", "xaxis": {"title": "Car Type"}, "yaxis": {"title": "Price (£)"}}
    }
    line = {
        "data": [{"x": df.groupby("year")["price"].mean().index,
                  "y": df.groupby("year")["price"].mean().values, "type": "line"}],
        "layout": {"title": f"Price Trend by Year in {country}"}
    }
    pie = {
        "data": [{"labels": df["car_type"].value_counts().index,
                  "values": df["car_type"].value_counts().values, "type": "pie"}],
        "layout": {"title": f"Car Types in {country}"}
    }

    # Push metrics async
    async_push_metric(
        measurement="used_car_dashboard",
        fields={
            "average_price": float(df["price"].mean()),
            "car_count": len(df),
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent
        },
        tags={"country": country}
    )

    return bar, line, pie

@app.callback(Output('car-image', 'src'), Input('image-interval', 'n_intervals'))
def update_image(_): return random.choice(CAR_IMAGES)

@app.callback(Output('price-bar', 'id'), Input('clear-cache-interval', 'n_intervals'))
def clear_cache(_):
    clear_country_cache()
    return "price-bar"

# ONLY run the development server when executed locally.
# Remove or comment this out when deploying with Gunicorn in production.
# if __name__ == "__main__":
#     logger.info("🚀 Running Dash app locally at http://0.0.0.0:8050")
#     app.run(debug=True, host="0.0.0.0", port=8050)
