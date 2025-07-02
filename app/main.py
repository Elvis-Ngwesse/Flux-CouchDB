import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import couchdb
import logging
import os
import pandas as pd
from dotenv import load_dotenv  # <-- added

# Load environment variables from .env file
load_dotenv()  # <-- added

# Setup logging
logging.basicConfig(filename='logs/app.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger()

# CouchDB connection
couchdb_url = os.getenv("COUCHDB_URL", "http://admin:admin@couchdb:5984/")
couch = couchdb.Server(couchdb_url)
db_name = "car_prices"

db = couch[db_name] if db_name in couch else couch.create(db_name)

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
    app.run_server(debug=True, host='0.0.0.0', port=8050)
