import random
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

DB_PATH = Path("operations_live.db")
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

CITIES = {
    "Chennai": {"lat": 13.0827, "lon": 80.2707},
    "Bengaluru": {"lat": 12.9716, "lon": 77.5946},
    "Mumbai": {"lat": 19.0760, "lon": 72.8777},
    "Delhi": {"lat": 28.6139, "lon": 77.2090},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
}

PRODUCTS = {
    "Laptop": (45000, 85000),
    "Phone": (12000, 65000),
    "Headphones": (1500, 9000),
    "Smart Watch": (2500, 18000),
    "Monitor": (7000, 28000),
    "Tablet": (8000, 45000),
}

WEATHER_CODE_MAP = {
    0: "Clear",
    1: "Mainly Clear",
    2: "Partly Cloudy",
    3: "Cloudy",
    45: "Fog",
    48: "Fog",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    61: "Light Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    71: "Light Snow",
    73: "Moderate Snow",
    75: "Heavy Snow",
    80: "Rain Showers",
    81: "Rain Showers",
    82: "Violent Rain Showers",
    95: "Thunderstorm",
    96: "Thunderstorm",
    99: "Thunderstorm",
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            product TEXT,
            price REAL,
            city TEXT,
            weather_flag TEXT
        )
    """)
    conn.commit()
    conn.close()


@st.cache_data(ttl=60)
def get_live_weather(city):
    info = CITIES[city]
    r = requests.get(
        WEATHER_API_URL,
        params={
            "latitude": info["lat"],
            "longitude": info["lon"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": "auto",
        },
        timeout=10,
    )
    r.raise_for_status()
    current = r.json().get("current", {})

    code = current.get("weather_code", -1)
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    condition = WEATHER_CODE_MAP.get(code, "Unknown")

    if code in {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}:
        impact = "Rain/Storm"
    elif temp is not None and temp >= 35:
        impact = "Heat"
    else:
        impact = "Normal"

    return {
        "City": city,
        "Condition": condition,
        "Temp (°C)": temp,
        "Humidity (%)": humidity,
        "Wind (km/h)": wind,
        "Impact": impact,
    }


def weather_snapshot():
    rows = []
    for city in CITIES:
        try:
            rows.append(get_live_weather(city))
        except Exception:
            rows.append({
                "City": city,
                "Condition": "Unavailable",
                "Temp (°C)": None,
                "Humidity (%)": None,
                "Wind (km/h)": None,
                "Impact": "Unknown",
            })
    return pd.DataFrame(rows)


def generate_sale():
    product = random.choice(list(PRODUCTS.keys()))
    low, high = PRODUCTS[product]
    city = random.choice(list(CITIES.keys()))

    try:
        weather = get_live_weather(city)
        impact = weather["Impact"]
    except Exception:
        impact = "Unknown"

    if impact == "Rain/Storm":
        high *= 0.92
    elif impact == "Heat":
        high *= 1.05

    return {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "product": product,
        "price": round(random.uniform(low, high), 2),
        "city": city,
        "weather_flag": impact,
    }


def insert_sale(row):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO sales(ts, product, price, city, weather_flag) VALUES (?, ?, ?, ?, ?)",
        (row["ts"], row["product"], row["price"], row["city"], row["weather_flag"]),
    )
    conn.commit()
    conn.close()


def simulator():
    while True:
        insert_sale(generate_sale())
        time.sleep(30)


def seed_if_empty():
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    conn.close()

    if count == 0:
        for _ in range(15):
            insert_sale(generate_sale())


def start_background_thread():
    if "sim_started" not in st.session_state:
        threading.Thread(target=simulator, daemon=True).start()
        st.session_state.sim_started = True


def load_sales():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM sales ORDER BY id DESC", conn)
    conn.close()
    return df


def sales_view():
    sales = load_sales()
    weather = weather_snapshot()

    total_revenue = float(sales["price"].sum()) if not sales.empty else 0
    order_volume = int(len(sales)) if not sales.empty else 0
    affected_orders = (
        int(sales["weather_flag"].isin(["Heat", "Rain/Storm"]).sum())
        if not sales.empty
        else 0
    )

    st.markdown("""
        <style>
        .stApp {
            background: linear-gradient(135deg, #08131a 0%, #0d1f28 100%);
            color: white;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 1rem;
        }
        .title-box {
            background: linear-gradient(90deg, rgba(0,180,216,.15), rgba(72,202,228,.05));
            border: 1px solid rgba(72,202,228,.25);
            padding: 18px 22px;
            border-radius: 16px;
            margin-bottom: 18px;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <div class="title-box">
            <h1 style="margin:0; color:#e9f8ff;">📡 Live Revenue Pulse + Weather Monitor</h1>
            <p style="margin:6px 0 0 0; color:#a8d8e8;">
                Real-time sales tracker with auto refresh, weather signals, and city-wise impact.
            </p>
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Revenue", f"₹{total_revenue:,.0f}")
    c2.metric("Current Order Volume", order_volume)
    c3.metric("Weather-Affected Orders", affected_orders)

    left, right = st.columns([1.5, 1])

    with left:
        st.subheader("Recent Sales Feed")
        if not sales.empty:
            st.dataframe(
                sales[["ts", "product", "price", "city", "weather_flag"]].head(12),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No sales yet.")

        st.subheader("Sales by City")
        if not sales.empty:
            city_rev = (
                sales.groupby("city", as_index=False)["price"]
                .sum()
                .sort_values("price", ascending=False)
            )
            st.bar_chart(city_rev.set_index("city"))
        else:
            st.info("City revenue data not available.")

        st.subheader("Sales Over Time")
        if not sales.empty:
            trend = sales.copy()
            trend["ts"] = pd.to_datetime(trend["ts"])
            trend = trend.sort_values("ts")
            trend = trend.groupby("ts", as_index=False)["price"].sum()
            trend = trend.set_index("ts")
            st.line_chart(trend)
        else:
            st.info("Trend data not available.")

    with right:
        st.subheader("Live Weather by City")
        st.dataframe(weather, use_container_width=True, hide_index=True)

        risk = weather[weather["Impact"].isin(["Heat", "Rain/Storm"])]
        if not risk.empty:
            cities = ", ".join(risk["City"].tolist())
            st.warning(f"⚠ Weather alert active in: {cities}")
        else:
            st.success("✅ No major weather disruption right now.")

        st.subheader("Weather Impact Summary")
        impact_counts = weather["Impact"].value_counts()
        st.bar_chart(impact_counts)


def main():
    st.set_page_config(
        page_title="Live Revenue Pulse",
        page_icon="📡",
        layout="wide"
    )

    init_db()
    seed_if_empty()
    start_background_thread()

    refresh = st.sidebar.slider("Auto refresh (sec)", 5, 60, 10)
    st.sidebar.markdown("### Dashboard Controls")
    st.sidebar.info("Fake sales every 30 seconds + live weather updates.")
    st.sidebar.code("python -m streamlit run live_dashboard.py")

    sales_view()

    time.sleep(refresh)
    st.rerun()


if __name__ == "__main__":
    main()