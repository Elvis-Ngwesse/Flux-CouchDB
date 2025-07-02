import couchdb
import random
from faker import Faker
import os
from dotenv import load_dotenv

load_dotenv()  # Load .env variables

fake = Faker()
couchdb_url = os.getenv("COUCHDB_URL", "http://admin:admin@localhost:5984/")
couch = couchdb.Server(couchdb_url)
db_name = "car_prices"
db = couch[db_name] if db_name in couch else couch.create(db_name)

eu_countries = [
    "Austria", "Belgium", "Bulgaria", "Croatia", "Czech Republic", "Denmark",
    "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland",
    "Italy", "Latvia", "Lithuania", "Netherlands", "Poland", "Portugal", "Spain", "United-Kingdom"
]

car_models = [
    # Your full list here
    "Volkswagen Golf", "Volkswagen Polo", "Volkswagen Passat", "Volkswagen Tiguan",
    # ... (rest omitted for brevity)
    "Subaru Outback", "Subaru Forester"
]

for country in eu_countries:
    sampled_cars = random.sample(car_models, k=random.randint(20, 30))
    for car in sampled_cars:
        for _ in range(random.randint(5, 10)):
            doc = {
                "country": country,
                "car_type": car,
                "price": random.randint(2000, 45000),
                "mileage": random.randint(10000, 200000),
                "year": random.randint(2005, 2024),
                "location": fake.city()
            }
            db.save(doc)

print("✅ Sample data inserted into CouchDB")
