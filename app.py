import streamlit as st
import time
import requests
import hmac
import hashlib
import numpy as np
import pandas as pd
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt

# =============================
# SECURITY - PASSWORD AUTH
# =============================
APP_PASSWORD = "t9W#3sYq@8vLc2Zb"
password = st.text_input("🔐 Enter password to access the app:", type="password")
if password != APP_PASSWORD:
    st.warning("Incorrect password.")
    st.stop()

# =============================
# API CREDENTIALS
# =============================
API_KEY = "exKUR5XB5c3H902y1T"
API_SECRET = "XXJxXO5i2py35wNlXxaqI7n1LATk4APfmSIb"
BASE_URL = "https://api.bybit.com"

# =============================
# PARAMETERS
# =============================
SYMBOL = "BTCUSDT"
INTERVAL = "15"
LIMIT = 200
STOP_LOSS_PCT = 5
TRADE_QUANTITY = 0.01

# =============================
# APP STATE
# =============================
if "trading_active" not in st.session_state:
    st.session_state.trading_active = False

# =============================
# FUNCTIONS
# =============================
def fetch_ohlcv():
    url = f"{BASE_URL}/v5/market/kline"
    params = {
        "category": "linear",
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": LIMIT
    }
    response = requests.get(url, params=params)
    data = response.json()

    if data.get("retCode") != 0:
        st.error(f"Error fetching data: {data.get('retMsg')}")
        return None

    df = pd.DataFrame(data["result"]["list"], columns=[
        "timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["close"] = df["close"].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
    return df

def train_lstm(prices):
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(prices.reshape(-1, 1))

    X, y = [], []
    window = 20
    for i in range(window, len(scaled)):
        X.append(scaled[i - window:i])
        y.append(scaled[i])

    X, y = np.array(X), np.array(y)

    model = Sequential()
    model.add(LSTM(50, return_sequences=True, input_shape=(X.shape[1], 1)))
    model.add(Dropout(0.2))
    model.add(LSTM(50))
    model.add(Dropout(0.2))
    model.add(Dense(1))
    model.compile(optimizer='adam', loss='mse')
    model.fit(X, y, epochs=10, batch_size=16, verbose=0)

    return model, scaler, X[-1].reshape(1, window, 1)

def generate_signature(params, secret):
    ordered = "&".join([f"{k}={params[k]}" for k in sorted(params)])
    return hmac.new(secret.encode(), ordered.encode(), hashlib.sha256).hexdigest()

def place_order(side, entry_price):
    url = f"{BASE_URL}/v5/order/create"
    timestamp = str(int(time.time() * 1000))
    stop_price = round(
        entry_price * (1 - STOP_LOSS_PCT/100) if side == "Buy"
        else entry_price * (1 + STOP_LOSS_PCT/100), 2
    )

    params = {
        "apiKey": API_KEY,
        "timestamp": timestamp,
        "recvWindow": "5000",
        "category": "linear",
        "symbol": SYMBOL,
        "side": side,
        "orderType": "Limit",
        "qty": str(TRADE_QUANTITY),
        "price": str(entry_price),
        "timeInForce": "GTC",
        "stopLoss": str(stop_price)
    }

    sign = generate_signature(params, API_SECRET)
    headers = {"X-BYBIT-API-KEY": API_KEY}
    params["sign"] = sign
    res = requests.post(url, headers=headers, data=params)
    st.info(f"📤 Order sent: {res.json()}")

def run_trading():
    df = fetch_ohlcv()
    if df is None or len(df) < 40:
        st.warning("Not enough data.")
        return

    prices = df["close"].values
    model, scaler, X_last = train_lstm(prices)
    prediction = model.predict(X_last)[0][0]
    predicted_price = scaler.inverse_transform([[prediction]])[0][0]
    current_price = prices[-1]

    st.subheader("💹 Market Analysis")
    st.write(f"**Current price**: {current_price:.2f}")
    st.write(f"**Predicted price**: {predicted_price:.2f}")

    fig, ax = plt.subplots()
    ax.plot(df["timestamp"], df["close"], label="Close Price")
    ax.set_title("Price History")
    ax.set_xlabel("Time")
    ax.set_ylabel("Price")
    ax.legend()
    st.pyplot(fig)

    if predicted_price > current_price * 1.002:
        st.success("🟢 Decision: BUY")
        place_order("Buy", round(current_price, 2))
    elif predicted_price < current_price * 0.998:
        st.error("🔴 Decision: SELL")
        place_order("Sell", round(current_price, 2))
    else:
        st.info("⏸️ No action taken (neutral forecast)")

# =============================
# UI
# =============================
st.title("🤖 AI Trading Bot for Bybit")

start = st.button("▶️ Start IA Trading")
stop = st.button("⛔ Stop IA Trading")

if start:
    st.session_state.trading_active = True
    st.success("Trading started.")

if stop:
    st.session_state.trading_active = False
    st.warning("Trading stopped. This is the last session of the day.")

if st.session_state.trading_active:
    run_trading()
