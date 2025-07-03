import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import couchdb
import logging
import os
import pandas as pd
from dotenv import load_dotenv  # <-- added
import time

# Load environment variables from .env file
load_dotenv()  # <-- added

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger()

# CouchDB connection
user = os.getenv("COUCHDB_USER", "admin")
password = os.getenv("COUCHDB_PASSWORD", "admin")
host = os.getenv("COUCHDB_HOST", "couchdb")
port = os.getenv("COUCHDB_PORT", "5984")

couchdb_url = f"http://{user}:{password}@{host}:{port}/"
couch = couchdb.Server(couchdb_url)
db_name = "car_prices"

# Retry logic to wait for CouchDB to be ready
couch = None
max_retries = 10
retry_delay = 3  # seconds

for attempt in range(max_retries):
    try:
        couch = couchdb.Server(couchdb_url)
        if db_name in couch:
            db = couch[db_name]
        else:
            db = couch.create(db_name)
        logger.info("Connected to CouchDB and accessed database successfully.")
        break
    except Exception as e:
        logger.warning(f"Attempt {attempt + 1}/{max_retries}: Could not connect to CouchDB - {e}")
        time.sleep(retry_delay)
else:
    logger.error("Failed to connect to CouchDB after several retries. Exiting.")
    raise SystemExit("Cannot connect to CouchDB")

app = dash.Dash(__name__)
server = app.server

# Dropdown options
def get_countries():
    countries = set()
    for doc_id in db:
        doc = db[doc_id]
        countries.add(doc.get('country', 'Unknown'))
    return sorted(list(countries))

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
    if not selected_country:
        return {"data": [], "layout": {"title": "Select a country"}}

    cars = [db[doc] for doc in db if db[doc].get('country') == selected_country]
    if not cars:
        return {"data": [], "layout": {"title": "No data for selected country"}}

    df = pd.DataFrame(cars)
    return {
        "data": [{"x": df["car_type"], "y": df["price"], "type": "bar"}],
        "layout": {"title": f"Used Car Prices in {selected_country}"}
    }

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8050)
