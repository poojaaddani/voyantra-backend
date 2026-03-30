import pandas as pd
import sqlite3
from sklearn.tree import DecisionTreeClassifier
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
import requests
app = Flask(__name__)
# -------- DATABASE SETUP --------

def init_db():
    conn = sqlite3.connect("voyantra.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destination TEXT,
            budget INTEGER,
            days INTEGER,
            transport TEXT,
            trip_type TEXT,
            total_cost INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()
# ---------------- ML DATASET ----------------

data = {
    "budget": [3000, 5000, 8000, 15000, 25000],
    "days": [2, 3, 3, 5, 7],
    "transport": [0, 0, 1, 1, 2],  # 0=Bus, 1=Train, 2=Flight
    "trip_type": ["Budget Trip", "Budget Trip", "Standard Trip", "Standard Trip", "Luxury Trip"]
}

df = pd.DataFrame(data)

X = df[["budget", "days", "transport"]]
y = df["trip_type"]

model = DecisionTreeClassifier()
model.fit(X, y)

# Transport Encoding
transport_map = {
    "Bus": 0,
    "Train": 1,
    "Flight": 2
}

# Database Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trips.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Model
class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    destination = db.Column(db.String(100))
    budget = db.Column(db.Integer)
    days = db.Column(db.Integer)
    transport = db.Column(db.String(50))
    total_cost = db.Column(db.Integer)

# Destination Data
trip_data = {
    "goa": {
        "type": "Beach Vacation",
        "image": "goa.jpg",
        "map": "https://www.google.com/maps?q=Goa&output=embed"
    },
    "manali": {
        "type": "Hill Station",
        "image": "manali.jpg",
        "map": "https://www.google.com/maps?q=Manali&output=embed"
    },
    "hyderabad": {
        "type": "City & Heritage",
        "image": "hyderabad.jpg",
        "map": "https://www.google.com/maps?q=Hyderabad&output=embed"
    }
}

# ---------------- HOME ROUTE ----------------
@app.route("/", methods=["GET", "POST"])
def home():
    suggestion = None
    image = None
    map_link = None
    total_cost = None

    if request.method == "POST":
        destination = request.form.get("destination").lower()
        budget = int(request.form.get("budget"))
        days = int(request.form.get("days"))
        transport = request.form.get("transport")

        # Stay cost
        stay_cost = days * 2000

        # Transport cost
        if transport == "flight":
            transport_cost = 8000
        elif transport == "train":
            transport_cost = 3000
        elif transport == "bus":
            transport_cost = 1500
        else:
            transport_cost = 4000

        total_cost = stay_cost + transport_cost

        # Destination image & map
        if destination in trip_data:
            image = trip_data[destination]["image"]
            map_link = trip_data[destination]["map"]

        # Save to database
        new_trip = Trip(
            destination=destination,
            budget=budget,
            days=days,
            transport=transport,
            total_cost=total_cost
        )
        db.session.add(new_trip)
        db.session.commit()

    return render_template("index.html",
                           suggestion=suggestion,
                           image=image,
                           map_link=map_link,
                           total_cost=total_cost)
@app.route("/plan", methods=["POST"])
def plan():

    destination = request.form["destination"]
    budget = int(request.form["budget"])
    days = int(request.form["days"])
    transport = request.form["transport"]

    transport_costs = {"Flight": 5000, "Train": 1500, "Bus": 800, "Car": 1000, "Bike": 500}
    transport_cost = transport_costs.get(transport, 0)

    hotel_per_day = 2000
    total_cost = (hotel_per_day * days) + transport_cost

    budget_status = "Within Budget ✅" if total_cost <= budget else "Budget Exceeded ❌"

    remaining_budget = budget - total_cost
    if remaining_budget > 2000:
        tip = f"You have ₹{remaining_budget} left! Consider upgrading your hotel."
    elif remaining_budget < 0:
        tip = f"You need ₹{-remaining_budget} more to cover this trip."
    else:
        tip = "Your budget matches perfectly!"

    map_link = f"https://www.google.com/maps/search/?api=1&query={destination}"

    # ---------------- Get Coordinates ----------------
    lat = None
    lon = None
    headers = {"User-Agent": "Voyantra-App"}

    try:
        geo_url = f"https://nominatim.openstreetmap.org/search?q={destination}&format=json"
        geo_response = requests.get(geo_url, headers=headers, timeout=10)

        if geo_response.status_code == 200:
            geo_data = geo_response.json()
            if geo_data:
                lat = float(geo_data[0]["lat"])
                lon = float(geo_data[0]["lon"])
    except Exception as e:
        print("Location Error:", e)

    # ---------------- Famous Places ----------------
    famous_places = []
    try:
        if lat and lon:
            geoapify_key = "33829af47b93439cbcc136ab8c147a8a"
            places_url = f"https://api.geoapify.com/v2/places?categories=tourism.sights&filter=circle:{lon},{lat},20000&limit=5&apiKey={geoapify_key}"
            places_resp = requests.get(places_url, timeout=10).json()

            for p in places_resp.get("features", []):
                name = p["properties"].get("name")
                if name:
                    famous_places.append(name)
    except Exception as e:
        print("Places API Error:", e)

    # ---------------- Hotels ----------------
    hotels = []
    try:
        if lat and lon:
            geoapify_key = "33829af47b93439cbcc136ab8c147a8a"
            hotel_url = f"https://api.geoapify.com/v2/places?categories=accommodation.hotel&filter=circle:{lon},{lat},20000&limit=5&apiKey={geoapify_key}"
            hotel_resp = requests.get(hotel_url, timeout=10).json()

            for h in hotel_resp.get("features", []):
                props = h["properties"]

                hotels.append({
                    "name": props.get("name", "Hotel"),
                    "address": props.get("address_line1", "Address not available"),
                    "rating": props.get("rating", "N/A"),
                    "lat": props.get("lat"),
                    "lon": props.get("lon")
                })
    except Exception as e:
        print("Hotels API Error:", e)

    # ---------------- Weather ----------------
    weather = {}
    try:
        weather_api_key = "2cc4d7574a01f9814e85bcb4b30ab525"
        weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={destination}&appid={weather_api_key}&units=metric"
        w = requests.get(weather_url, timeout=10).json()

        weather = {
            "temp": w["main"]["temp"],
            "description": w["weather"][0]["description"],
            "humidity": w["main"]["humidity"],
            "wind_speed": w["wind"]["speed"]
        }
    except Exception as e:
        print("Weather API Error:", e)

    return render_template(
        "index.html",
        destination=destination,
        total_cost=total_cost,
        budget_status=budget_status,
        map_link=map_link,
        famous_places=famous_places,
        hotels=hotels,
        weather=weather,
        transport=transport,
        tip=tip
    )
from flask import jsonify

@app.route("/api/plan", methods=["GET"])
def api_plan():

    destination = request.args.get("destination")
    budget = int(request.args.get("budget"))
    days = int(request.args.get("days"))
    transport = request.args.get("transport")

    # Cost calculation
    transport_costs = {"Flight": 5000, "Train": 1500, "Bus": 800}
    transport_cost = transport_costs.get(transport, 0)

    hotel_per_day = 2000
    total_cost = (hotel_per_day * days) + transport_cost

    # Weather
    weather_api_key = "2cc4d7574a01f9814e85bcb4b30ab525"
    weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={destination}&appid={weather_api_key}&units=metric"
    w = requests.get(weather_url).json()

    weather = {
        "temp": w["main"]["temp"],
        "description": w["weather"][0]["description"]
    }

    return jsonify({
        "destination": destination,
        "total_cost": total_cost,
        "weather": weather
    })
@app.route("/get_trip")
def get_trip():
    destination = request.args.get("destination")

    return {
        "city": destination,
        "temperature": 30,
        "condition": "clear sky",
        "humidity": 60
    }
@app.route("/book")
def book():
    name = request.args.get("name")
    rating = request.args.get("rating")
    address = request.args.get("address")

    return render_template(
        "booking.html",
        name=name,
        rating=rating,
        address=address
    )
@app.route("/confirm-booking", methods=["POST"])
def confirm_booking():
    customer_name = request.form["customer_name"]
    hotel_name = request.form["hotel_name"]
    return render_template(
        "success.html",
        customer_name=customer_name,
        hotel_name=hotel_name
    )
@app.route("/dashboard")
def dashboard():
    conn = sqlite3.connect("voyantra.db")
    c = conn.cursor()
    c.execute("SELECT transport FROM trips")
    data = c.fetchall()
    conn.close()

    transports = [row[0] for row in data]

    from collections import Counter
    transport_count = Counter(transports)

    return render_template("dashboard.html", transport_count=transport_count)

# ---------------- HISTORY ROUTE ----------------
@app.route("/history")
def history():
    trips = Trip.query.all()
    return render_template("history.html", trips=trips)
    

import os

@app.route("/")
def home():
    return "Backend Running!"

import os

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
