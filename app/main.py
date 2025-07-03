import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import couchdb
import logging
import os
import pandas as pd
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# Setup logging with file and console handlers (optional)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger()

# CouchDB connection info from environment variables
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")

couchdb_url = f"http://{user}:{password}@{host}:{port}/"
logger.debug(f"Constructed CouchDB URL: {couchdb_url}")

# Initialize CouchDB connection with retry logic
couch = None
max_retries = 10
retry_delay = 3  # seconds
db_name = "car_prices"

for attempt in range(max_retries):
    try:
        logger.info(f"Trying to connect to CouchDB (attempt {attempt + 1}/{max_retries})")
        couch = couchdb.Server(couchdb_url)
        if db_name in couch:
            db = couch[db_name]
            logger.info(f"Database '{db_name}' found in CouchDB server.")
        else:
            db = couch.create(db_name)
            logger.info(f"Database '{db_name}' created.")
        break
    except Exception as e:
        logger.warning(f"Attempt {attempt + 1} failed: Could not connect to CouchDB - {e}")
        time.sleep(retry_delay)
else:
    logger.error("Failed to connect to CouchDB after several retries. Exiting application.")
    raise SystemExit("Cannot connect to CouchDB")

app = dash.Dash(__name__)
server = app.server

def get_countries():
    logger.info("Fetching countries from the database")
    countries = set()
    try:
        for doc_id in db:
            doc = db[doc_id]
            country = doc.get('country', 'Unknown')
            countries.add(country)
            logger.debug(f"Found country: {country} in document ID: {doc_id}")
        sorted_countries = sorted(list(countries))
        logger.info(f"Total unique countries found: {len(sorted_countries)}")
        return sorted_countries
    except Exception as e:
        logger.error(f"Error fetching countries: {e}")
        return []

app.layout = html.Div([
    html.H1("EU Used Car Market Dashboard (£)"),
    dcc.Dropdown(
        id='country-dropdown',
        options=[{'label': c, 'value': c} for c in get_countries()],
        placeholder="Select a country",
    ),
    dcc.Graph(id='price-chart'),
])

@app.callback(Output('price-chart', 'figure'), [Input('country-dropdown', 'value')])
def update_chart(selected_country):
    logger.info(f"Callback triggered with selected_country={selected_country}")
    if not selected_country:
        logger.debug("No country selected yet.")
        return {"data": [], "layout": {"title": "Select a country"}}

    try:
        cars = [db[doc] for doc in db if db[doc].get('country') == selected_country]
        logger.debug(f"Number of cars found for {selected_country}: {len(cars)}")
    except Exception as e:
        logger.error(f"Error retrieving car data for {selected_country}: {e}")
        return {"data": [], "layout": {"title": "Error loading data"}}

    if not cars:
        logger.warning(f"No data found for country: {selected_country}")
        return {"data": [], "layout": {"title": "No data for selected country"}}

    df = pd.DataFrame(cars)
    logger.debug(f"DataFrame created with shape: {df.shape}")

    figure = {
        "data": [{"x": df["car_type"], "y": df["price"], "type": "bar"}],
        "layout": {"title": f"Used Car Prices in {selected_country}"}
    }
    logger.info(f"Returning chart figure for country: {selected_country}")
    return figure

if __name__ == "__main__":
    logger.info("Starting Dash app on http://0.0.0.0:8050")
    app.run(debug=True, host='0.0.0.0', port=8050)
