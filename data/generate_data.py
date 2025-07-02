import couchdb
import random
import faker

fake = faker.Faker()
couch = couchdb.Server("http://admin:admin@localhost:5984/")
db_name = "car_prices"
db = couch[db_name] if db_name in couch else couch.create(db_name)

eu_countries = ["Austria", "Belgium", "Bulgaria", "Croatia", "Czech Republic", "Denmark",
                "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland",
                "Italy", "Latvia", "Lithuania", "Netherlands", "Poland", "Portugal", "Spain", "United-Kingdom"]

car_models = [
    "Volkswagen Golf", "Volkswagen Polo", "Volkswagen Passat", "Volkswagen Tiguan",
    "Ford Fiesta", "Ford Focus", "Ford Mondeo", "Ford Kuga",
    "Peugeot 208", "Peugeot 308", "Peugeot 3008", "Peugeot 2008",
    "Renault Clio", "Renault Megane", "Renault Captur", "Renault Kadjar",
    "Opel Corsa", "Opel Astra", "Opel Insignia", "Opel Mokka",
    "Fiat Panda", "Fiat 500", "Fiat Punto", "Fiat Tipo",
    "Toyota Yaris", "Toyota Corolla", "Toyota Aygo", "Toyota RAV4",
    "Skoda Octavia", "Skoda Fabia", "Skoda Superb", "Skoda Karoq",
    "Dacia Sandero", "Dacia Duster", "Dacia Logan", "Dacia Jogger",
    "Audi A3", "Audi A4", "Audi A6", "Audi Q3",
    "BMW 1 Series", "BMW 3 Series", "BMW 5 Series", "BMW X1",
    "Mercedes A-Class", "Mercedes C-Class", "Mercedes E-Class", "Mercedes GLA",
    "Citroen C3", "Citroen C4", "Citroen C1", "Citroen C5 Aircross",
    "Hyundai i10", "Hyundai i20", "Hyundai i30", "Hyundai Tucson",
    "Kia Picanto", "Kia Ceed", "Kia Sportage", "Kia Rio",
    "Nissan Micra", "Nissan Juke", "Nissan Qashqai", "Nissan X-Trail",
    "SEAT Ibiza", "SEAT Leon", "SEAT Arona", "SEAT Ateca",
    "Honda Jazz", "Honda Civic", "Honda CR-V", "Honda HR-V",
    "Volvo V40", "Volvo XC40", "Volvo V60", "Volvo XC60",
    "Mazda 2", "Mazda 3", "Mazda 6", "Mazda CX-5",
    "Mini Cooper", "Mini Clubman", "Mini Countryman", "Mini One",
    "Suzuki Swift", "Suzuki Vitara", "Suzuki SX4", "Suzuki Ignis",
    "Mitsubishi ASX", "Mitsubishi Outlander", "Mitsubishi Eclipse Cross",
    "Jeep Renegade", "Jeep Compass", "Jeep Cherokee",
    "Alfa Romeo Giulia", "Alfa Romeo Giulietta", "Alfa Romeo Stelvio",
    "Tesla Model 3", "Tesla Model S", "Tesla Model Y", "Tesla Model X",
    "Hyundai Santa Fe", "Hyundai Kona", "Kia Stinger", "Kia Sorento",
    "Toyota Camry", "Toyota Land Cruiser", "Mazda CX-3", "Mazda CX-30",
    "Ford Mustang", "Ford Edge", "Chevrolet Cruze", "Chevrolet Tahoe",
    "Nissan Leaf", "Nissan Altima", "Honda Accord", "Honda Pilot",
    "Volkswagen Arteon", "Volkswagen Tiguan Allspace", "Audi Q5", "Audi Q7",
    "BMW X3", "BMW X5", "Mercedes GLC", "Mercedes GLE",
    "Peugeot 508", "Peugeot 5008", "Citroen C5", "Citroen Berlingo",
    "Renault Twingo", "Renault Zoe", "Fiat 124 Spider", "Fiat 500X",
    "Seat Tarraco", "Seat Alhambra", "Skoda Kodiaq", "Skoda Scala",
    "Jeep Wrangler", "Jeep Grand Cherokee", "Tesla Model X Plaid", "Tesla Model S Plaid",
    "Mini Electric", "Suzuki Ignis Hybrid", "Mitsubishi Pajero", "Mitsubishi L200",
    "Land Rover Discovery", "Land Rover Defender", "Volvo XC90", "Volvo S90",
    "Subaru Outback", "Subaru Forester"
]

for country in eu_countries:
    for car in random.sample(car_models, k=random.randint(20, 30)):
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
