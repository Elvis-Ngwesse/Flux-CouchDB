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
import psutil  # For system metrics
import threading

# Load environment variables
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

# CouchDB connection
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")
couchdb_url = f"http://{user}:{password}@{host}:{port}/"
db_name = "car_prices"

# InfluxDB connection
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_DB = os.getenv("INFLUXDB_DB", "car_metrics")

def ensure_influxdb_db_exists():
    logger.info(f"Ensuring InfluxDB database '{INFLUXDB_DB}' exists...")
    try:
        url = f"{INFLUXDB_URL}/query"
        params = {"q": f"CREATE DATABASE {INFLUXDB_DB}"}
        r = requests.post(url, params=params)
        if r.status_code != 200:
            logger.warning(f"Failed to create DB: {r.status_code} {r.text}")
        else:
            logger.info(f"InfluxDB database '{INFLUXDB_DB}' ensured.")
    except Exception as e:
        logger.error(f"Error creating InfluxDB DB: {e}")

def format_field_value(value):
    if isinstance(value, str):
        return f'"{value.replace("\\", "\\\\").replace("\"", "\\\"")}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return f"{value}i"
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

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=line, timeout=5)
            if resp.status_code == 204:
                logger.debug(f"Metric pushed: {line}")
                return True
            logger.warning(f"Attempt {attempt+1}: {resp.status_code} {resp.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Attempt {attempt+1} error: {e}")

        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            logger.info(f"Retrying in {delay}s...")
            time.sleep(delay)
        else:
            logger.error(f"Failed to push metric: {line}")
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
                "app": "car-dashboard"
            }
        )
    except Exception as e:
        logger.error(f"Error pushing resource metrics: {e}")

# Start resource metrics loop in background
def metrics_loop():
    while True:
        push_resource_metrics()
        time.sleep(60)

threading.Thread(target=metrics_loop, daemon=True).start()

# Connect to CouchDB
couch = None
for attempt in range(10):
    try:
        logger.info(f"Connecting to CouchDB (attempt {attempt+1})")
        couch = couchdb.Server(couchdb_url)
        if db_name in couch:
            db = couch[db_name]
        else:
            db = couch.create(db_name)
        logger.info(f"Connected to DB: {db_name}")
        break
    except Exception as e:
        logger.warning(f"CouchDB connection failed: {e}")
        time.sleep(3)
else:
    raise SystemExit("Failed to connect to CouchDB")

# Ensure InfluxDB DB exists
ensure_influxdb_db_exists()

# Dash App
app = dash.Dash(__name__)
server = app.server

CAR_IMAGES = [
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/car-49278_1280.jpg",
    "https://cdn.pixabay.com/photo/2015/01/19/13/51/car-604019_1280.jpg",
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/auto-49277_1280.jpg",
]

def get_countries():
    countries = set()
    try:
        for doc_id in db:
            doc = db[doc_id]
            countries.add(doc.get('country', 'Unknown'))
    except Exception as e:
        logger.error(f"Error fetching countries: {e}")
    return sorted(list(countries))

app.layout = html.Div(style={'fontFamily': 'Arial', 'padding': '20px'}, children=[
    html.H1("🚗 Used Car Market Dashboard (£)", style={'textAlign': 'center', 'color': '#003366'}),
    html.Div([
        html.Img(src=random.choice(CAR_IMAGES),
                 style={'width': '100%', 'maxHeight': '300px', 'objectFit': 'cover'}),
    ]),
    html.Br(),
    html.Div([
        dcc.Dropdown(
            id='country-dropdown',
            options=[{'label': c, 'value': c} for c in get_countries()],
            placeholder="Select a country",
        )
    ], style={'padding': '10px 0'}),

    dcc.Interval(id='interval', interval=60 * 1000, n_intervals=0, disabled=True),

    html.Div([
        dcc.Graph(id='price-bar'),
        dcc.Graph(id='price-line'),
        dcc.Graph(id='car-pie'),
    ])
])

@app.callback(
    [Output('price-bar', 'figure'),
     Output('price-line', 'figure'),
     Output('car-pie', 'figure'),
     Output('interval', 'disabled')],
    [Input('country-dropdown', 'value'),
     Input('interval', 'n_intervals')]
)
def update_graphs(selected_country, n_intervals):
    if not selected_country:
        return (
            {"data": [], "layout": {"title": "Select a country"}},
            {"data": [], "layout": {"title": "Select a country"}},
            {"data": [], "layout": {"title": "Select a country"}},
            True
        )

    try:
        cars = [db[doc] for doc in db if db[doc].get('country') == selected_country]
        if not cars:
            return (
                {"data": [], "layout": {"title": "No data"}},
                {"data": [], "layout": {"title": "No data"}},
                {"data": [], "layout": {"title": "No data"}},
                True
            )
        df = pd.DataFrame(cars)
    except Exception as e:
        logger.error(f"Error retrieving data: {e}")
        return (
            {"data": [], "layout": {"title": "Error"}},
            {"data": [], "layout": {"title": "Error"}},
            {"data": [], "layout": {"title": "Error"}},
            True
        )

    price_bar = {
        "data": [{"x": df["car_type"], "y": df["price"], "type": "bar"}],
        "layout": {"title": f"Prices in {selected_country}", "xaxis": {"title": "Type"}, "yaxis": {"title": "£"}}
    }

    year_avg = df.groupby("year")["price"].mean().reset_index()
    price_line = {
        "data": [{"x": year_avg["year"], "y": year_avg["price"], "type": "line"}],
        "layout": {"title": f"Trend in {selected_country}", "xaxis": {"title": "Year"}, "yaxis": {"title": "Avg £"}}
    }

    type_counts = df["car_type"].value_counts()
    car_pie = {
        "data": [{"labels": type_counts.index, "values": type_counts.values, "type": "pie"}],
        "layout": {"title": f"Car Types in {selected_country}"}
    }

    return price_bar, price_line, car_pie, False

if __name__ == "__main__":
    logger.info("Starting Dash app on http://0.0.0.0:8050")
    app.run(debug=True, host='0.0.0.0', port=8050)
