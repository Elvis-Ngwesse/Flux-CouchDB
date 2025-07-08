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
        logging.StreamHandler()  # Also logs to stdout for Kubernetes logging
        ]
)
logger = logging.getLogger()

# CouchDB connection details
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")
couchdb_url = f"http://{user}:{password}@{host}:{port}/"
db_name = "car_prices"

# InfluxDB connection details from env
INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_DB = os.getenv("INFLUXDB_DB", "car_metrics")  # fallback for v1.8

def ensure_influxdb_db_exists():
    logger.info(f"Ensuring InfluxDB database '{INFLUXDB_DB}' exists...")
    try:
        url = f"{INFLUXDB_URL}/query"
        params = {
            "q": f"CREATE DATABASE {INFLUXDB_DB}"
        }
        r = requests.post(url, params=params)
        if r.status_code != 200:
            logger.warning(f"Failed to create DB: {r.status_code} {r.text}")
        else:
            logger.info(f"InfluxDB database '{INFLUXDB_DB}' ensured.")
    except Exception as e:
        logger.error(f"Error creating InfluxDB DB: {e}")

def format_field_value(value):
    if isinstance(value, str):
        # Escape double quotes and backslashes inside strings
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
    return re.sub(r'[ ,=]', '_', value)

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
        tag_str = ",".join(f"{k}={sanitize_tag_value(str(v))}" for k, v in tags.items())
        line += f",{tag_str}"
    field_str = ",".join(f"{k}={format_field_value(v)}" for k, v in fields.items())
    line += f" {field_str}"
    if timestamp:
        line += f" {timestamp}"

    url = f"{INFLUXDB_URL}/write?db={INFLUXDB_DB}&precision=ns"
    headers = {
        "Content-Type": "text/plain"
    }

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

# Retry logic for CouchDB connection
couch = None
max_retries = 10
retry_delay = 3
for attempt in range(max_retries):
    try:
        logger.info(f"Trying to connect to CouchDB (attempt {attempt + 1}/{max_retries})")
        couch = couchdb.Server(couchdb_url)
        if db_name in couch:
            db = couch[db_name]
            logger.info(f"Database '{db_name}' found.")
        else:
            db = couch.create(db_name)
            logger.info(f"Database '{db_name}' created.")
        break
    except Exception as e:
        logger.warning(f"Connection failed: {e}")
        time.sleep(retry_delay)
else:
    raise SystemExit("Failed to connect to CouchDB")

# Ensure InfluxDB database exists
ensure_influxdb_db_exists()

# Initialize Dash app
app = dash.Dash(__name__)
server = app.server

# Fetch all countries from the DB
def get_countries():
    logger.info("Fetching countries...")
    countries = set()
    try:
        for doc_id in db:
            doc = db[doc_id]
            countries.add(doc.get('country', 'Unknown'))
        return sorted(list(countries))
    except Exception as e:
        logger.error(f"Error fetching countries: {e}")
        return []

# Sample car banner images
CAR_IMAGES = [
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/car-49278_1280.jpg",
    "https://cdn.pixabay.com/photo/2015/01/19/13/51/car-604019_1280.jpg",
    "https://cdn.pixabay.com/photo/2012/05/29/00/43/auto-49277_1280.jpg",
]

# App layout
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

    # Interval for auto-refresh
    dcc.Interval(id='interval', interval=60 * 1000, n_intervals=0, disabled=True),

    html.Div([
        dcc.Graph(id='price-bar'),
        dcc.Graph(id='price-line'),
        dcc.Graph(id='car-pie'),
    ])
])

# Callback to update graphs + control interval enable/disable
@app.callback(
    [Output('price-bar', 'figure'),
     Output('price-line', 'figure'),
     Output('car-pie', 'figure'),
     Output('interval', 'disabled')],
    [Input('country-dropdown', 'value'),
     Input('interval', 'n_intervals')]
)
def update_graphs(selected_country, n_intervals):
    logger.info(f"Dashboard refresh. Country={selected_country}, Interval={n_intervals}")

    if not selected_country:
        return (
            {"data": [], "layout": {"title": "Select a country"}},
            {"data": [], "layout": {"title": "Select a country"}},
            {"data": [], "layout": {"title": "Select a country"}},
            True  # Disable interval when no country selected
        )

    try:
        cars = [db[doc] for doc in db if db[doc].get('country') == selected_country]
        if not cars:
            logger.info("No car data found for selected country.")
            return (
                {"data": [], "layout": {"title": "No data"}},
                {"data": [], "layout": {"title": "No data"}},
                {"data": [], "layout": {"title": "No data"}},
                True  # Disable interval if no data
            )
        df = pd.DataFrame(cars)
    except Exception as e:
        logger.error(f"Failed to retrieve data: {e}")
        return (
            {"data": [], "layout": {"title": "Error"}},
            {"data": [], "layout": {"title": "Error"}},
            {"data": [], "layout": {"title": "Error"}},
            True  # Disable interval on error
        )

    # Bar chart: price per car type
    price_bar = {
        "data": [{"x": df["car_type"], "y": df["price"], "type": "bar", "name": "Car Prices"}],
        "layout": {"title": f"Used Car Prices in {selected_country}", "xaxis": {"title": "Car Type"},
                   "yaxis": {"title": "Price (£)"}}
    }

    # Line chart: average price by year
    year_avg = df.groupby("year")["price"].mean().reset_index()
    price_line = {
        "data": [{"x": year_avg["year"], "y": year_avg["price"], "type": "line", "name": "Average Price"}],
        "layout": {"title": f"Avg Car Price Trend by Year in {selected_country}", "xaxis": {"title": "Year"},
                   "yaxis": {"title": "Average Price (£)"}}
    }

    # Pie chart: car type distribution
    type_counts = df["car_type"].value_counts()
    car_pie = {
        "data": [{"labels": type_counts.index, "values": type_counts.values, "type": "pie"}],
        "layout": {"title": f"Car Type Distribution in {selected_country}"}
    }

    # Push metrics to InfluxDB with retries and logging
    avg_price = df["price"].mean()
    count_cars = len(df)
    push_metric(
        measurement="used_car_market",
        fields={
            "average_price": float(avg_price),
            "car_count": count_cars
        },
        tags={
            "country": selected_country
        }
    )

    return price_bar, price_line, car_pie, False  # Enable interval

# Run app
if __name__ == "__main__":
    logger.info("Starting Dash app on http://0.0.0.0:8050")
    app.run(debug=True, host='0.0.0.0', port=8050)
