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

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger()

# CouchDB connection details
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")
couchdb_url = f"http://{user}:{password}@{host}:{port}/"
db_name = "car_prices"

# Retry logic
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

# Start Dash app
app = dash.Dash(__name__)
server = app.server


# Get all countries in DB
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


# Some car banner images
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

    # Interval for auto-refresh (disabled by default)
    dcc.Interval(id='interval', interval=60 * 1000, n_intervals=0, disabled=True),

    html.Div([
        dcc.Graph(id='price-bar'),
        dcc.Graph(id='price-line'),
        dcc.Graph(id='car-pie'),
    ])
])


# Callback to update graphs + control interval
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
            True  # disable auto-refresh
        )

    try:
        cars = [db[doc] for doc in db if db[doc].get('country') == selected_country]
        if not cars:
            return (
                {"data": [], "layout": {"title": "No data"}},
                {"data": [], "layout": {"title": "No data"}},
                {"data": [], "layout": {"title": "No data"}},
                False
            )
        df = pd.DataFrame(cars)
    except Exception as e:
        logger.error(f"Failed to retrieve data: {e}")
        return (
            {"data": [], "layout": {"title": "Error"}},
            {"data": [], "layout": {"title": "Error"}},
            {"data": [], "layout": {"title": "Error"}},
            False
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

    return price_bar, price_line, car_pie, False  # Enable interval


# Run app
if __name__ == "__main__":
    logger.info("Starting Dash app on http://0.0.0.0:8050")
    app.run(debug=True, host='0.0.0.0', port=8050)
