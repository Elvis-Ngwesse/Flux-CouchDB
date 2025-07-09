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

# Load environment variables
load_dotenv()

# Logging setup (set level to DEBUG for max verbosity)
log_dir = "/app/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

# Clear existing handlers first to avoid duplicates
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.DEBUG,  # <-- Set to DEBUG for detailed logs
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True  # Make sure this config is applied even if logging was configured before
)
logger = logging.getLogger(__name__)

# CouchDB config
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")
couchdb_url = f"http://{user}:{password}@{host}:{port}/"
db_name = "car_prices"

# InfluxDB config
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUXDB_DB = os.getenv("INFLUXDB_DB", "car_metrics")

def ensure_influxdb_db_exists():
    try:
        url = f"{INFLUXDB_URL}/query"
        r = requests.post(url, params={"q": f"CREATE DATABASE {INFLUXDB_DB}"})
        if r.status_code == 200:
            logger.info(f"✅ InfluxDB DB '{INFLUXDB_DB}' ensured.")
        else:
            logger.warning(f"⚠️ Failed to ensure InfluxDB DB: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"❌ InfluxDB check failed: {e}")

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
    return re.sub(r'[ ,=]', '_', value)

def push_metric(measurement, fields, tags=None, timestamp=None, max_retries=5, base_delay=1):
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
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=line, timeout=5)
            if resp.status_code == 204:
                logger.debug(f"✅ Metric pushed: {line}")
                return True
            else:
                logger.warning(f"❌ InfluxDB push failed ({resp.status_code}): {resp.text}")
        except requests.RequestException as e:
            logger.error(f"🚨 Exception pushing metric: {e}")
        delay = base_delay * (2 ** (attempt - 1))
        logger.info(f"⏳ Retrying in {delay}s...")
        time.sleep(delay)
    logger.error("❌ Max retries reached. Failed to push metrics.")
    return False

# CouchDB connection
couch = None
for attempt in range(10):
    try:
        logger.info(f"🔌 Connecting to CouchDB (attempt {attempt+1})")
        couch = couchdb.Server(couchdb_url)
        db = couch[db_name] if db_name in couch else couch.create(db_name)
        logger.info("✅ Connected to CouchDB successfully.")
        break
    except Exception as e:
        logger.warning(f"⚠️ CouchDB connection failed: {e}")
        time.sleep(3)
else:
    logger.critical("❌ Could not connect to CouchDB. Exiting.")
    raise SystemExit("❌ Could not connect to CouchDB")

ensure_influxdb_db_exists()

CAR_IMAGES = [
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/car-49278_1280.jpg",
    "https://cdn.pixabay.com/photo/2015/01/19/13/51/car-604019_1280.jpg",
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/auto-49277_1280.jpg",
]

flask_server = Flask(__name__)
@flask_server.route("/health")
def health():
    logger.debug("Health check endpoint hit")
    return "OK", 200

app = dash.Dash(__name__, server=flask_server)
server = app.server

def get_countries():
    logger.debug("Fetching list of countries from CouchDB...")
    countries = set()
    try:
        for doc_id in db:
            country = db[doc_id].get('country', 'Unknown')
            countries.add(country)
        logger.debug(f"Found countries: {countries}")
    except Exception as e:
        logger.error(f"❌ Error fetching countries: {e}")
    return sorted(list(countries))

countries_list = get_countries()

app.layout = html.Div(style={'fontFamily': 'Arial', 'padding': '20px'}, children=[
    html.H1("🚗 Used Car Market Dashboard (£)", style={'textAlign': 'center'}),
    html.Img(id="car-image", src=random.choice(CAR_IMAGES),
             style={'width': '100%', 'maxHeight': '300px', 'objectFit': 'cover'}),
    html.Br(),
    dcc.Dropdown(
        id='country-dropdown',
        options=[{'label': c, 'value': c} for c in countries_list],
        value="Cameroon" if "Cameroon" in countries_list else (countries_list[0] if countries_list else None),
        placeholder="Select a country",
        style={'marginBottom': '10px'}
    ),
    dcc.Interval(id='interval', interval=60000, n_intervals=0),
    dcc.Interval(id='image-interval', interval=60000, n_intervals=0),
    dcc.Graph(id='price-bar'),
    dcc.Graph(id='price-line'),
    dcc.Graph(id='car-pie'),
])

@app.callback(
    [Output('price-bar', 'figure'),
     Output('price-line', 'figure'),
     Output('car-pie', 'figure')],
    [Input('country-dropdown', 'value'),
     Input('interval', 'n_intervals')]
)
def update_graphs(country, _):
    logger.debug(f"update_graphs called with country={country}")
    if not country:
        logger.info("No country selected yet")
        fig = {"data": [], "layout": {"title": "Select a country"}}
        return fig, fig, fig

    try:
        cars = [db[doc] for doc in db if db[doc].get('country') == country]
        if not cars:
            logger.info(f"No car data for country: {country}")
            fig = {"data": [], "layout": {"title": "No data"}}
            return fig, fig, fig
        df = pd.DataFrame(cars)
        logger.debug(f"Fetched {len(df)} records for country {country}")
    except Exception as e:
        logger.error(f"❌ Failed to fetch car data: {e}")
        fig = {"data": [], "layout": {"title": "Error"}}
        return fig, fig, fig

    bar = {
        "data": [{"x": df["car_type"], "y": df["price"], "type": "bar"}],
        "layout": {"title": f"Car Prices in {country}", "xaxis": {"title": "Car Type"}, "yaxis": {"title": "Price (£)"}}
    }

    line = {
        "data": [{"x": df.groupby("year")["price"].mean().index,
                  "y": df.groupby("year")["price"].mean().values,
                  "type": "line"}],
        "layout": {"title": f"Price Trend by Year in {country}"}
    }

    pie = {
        "data": [{"labels": df["car_type"].value_counts().index,
                  "values": df["car_type"].value_counts().values,
                  "type": "pie"}],
        "layout": {"title": f"Car Type Distribution in {country}"}
    }

    logger.debug(f"Pushing metrics for country {country}: avg_price={df['price'].mean()}, count={len(df)}")
    push_metric(
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

@app.callback(
    Output('car-image', 'src'),
    Input('image-interval', 'n_intervals')
)
def update_image(_):
    logger.debug("Updating car image")
    return random.choice(CAR_IMAGES)

if __name__ == "__main__":
    logger.info("🚀 Dash app running at http://0.0.0.0:8050")
    app.run(debug=True, host='0.0.0.0', port=8050)
