import requests
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

BOT_TOKEN = "8264008675:AAEHzakAXPZeNVZKWlvYHRWboyjAuUhg0QM"
FOREX_CHAT_ID = "-1004292142406"

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Kanak Sniper Engine: Optimized Volume Matrix Live!")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_fake_server():
    import os
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DummyServer)
    server.serve_forever()

def get_current_forex_sessions():
    now_utc = datetime.utcnow()
    now_bst = now_utc + timedelta(hours=6)
    current_hour = now_bst.hour
    sessions = []
    if 4 <= current_hour < 13: sessions.append("Sydney 🇦🇺")
    if 6 <= current_hour < 15: sessions.append("Tokyo 🇯🇵")
    if 13 <= current_hour < 22: sessions.append("London 🇬🇧")
    if current_hour >= 18 or current_hour < 3: sessions.append("New York 🇺🇸")
    return ", ".join(sessions) if sessions else "Live Market"

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    return 100 - (100 / (1 + (avg_gain / avg_loss)))

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(window=period).mean()

def calculate_cmf(df, period=20):
    mf_multiplier = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['High'] - df['Low'])
    mf_multiplier = mf_multiplier.fillna(0)
    volume = (df['High'] - df['Low']).replace(0, 0.00001)
    mf_volume = mf_multiplier * volume
    return mf_volume.rolling(window=period).sum() / volume.rolling(window=period).sum()

def fetch_candles(ticker_symbol, interval, range_str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?range={range_str}&interval={interval}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200: return None
    result = response.json()['chart']['result'][0]
    df = pd.DataFrame({
        'Open': result['indicators']['quote'][0]['open'],
        'High': result['indicators']['quote'][0]['high'],
        'Low': result['indicators']['quote'][0]['low'],
        'Close': result['indicators']['quote'][0]['close']
    }, index=pd.to_datetime(result['timestamp'], unit='s')).dropna()
    return df

def generate_signal(ticker_symbol, display_name):
    try:
        df_5m = fetch_candles(ticker_symbol, "5m", "5d")
        if df_5m is None or len(df_5m) < 80:
            return {"status": "NO_SIGNAL", "price": 0.0}

        is_jpy = "JPY" in ticker_symbol
        dec_places = 2 if is_jpy else 4

        # 3MA Calculation
        df_5m['EMA_Green'] = calculate_ema(df_5m['Close'], 12)
        df_5m['EMA_Yellow'] = calculate_ema(df_5m['Close'], 26)
        df_5m['EMA_Red'] = calculate_ema(df_5m['Close'], 45)

        # Technicals
        df_5m['RSI'] = calculate_rsi(df_5m['Close'])
        df_5m['ATR'] = calculate_atr(df_5m)
        df_5m['MACD'] = calculate_ema(df_5m['Close'], 12) - calculate_ema(df_5m['Close'], 26)
        df_5m['MACD_signal'] = calculate_ema(df_5m['MACD'], 9)

        latest = df_5m.iloc[-1]
        prev = df_5m.iloc[-2]

        # 3MA Cross Logic
        green_cross_up = (prev['EMA_Green'] <= prev['EMA_Yellow'] or prev['EMA_Green'] <= prev['EMA_Red']) and \
                         (latest['EMA_Green'] > latest['EMA_Yellow'] and latest['EMA_Green'] > latest['EMA_Red'])
        
        green_cross_down = (prev['EMA_Green'] >= prev['EMA_Yellow'] or prev['EMA_Green'] >= prev['EMA_Red']) and \
                           (latest['EMA_Green'] < latest['EMA_Yellow'] and latest['EMA_Green'] < latest['EMA_Red'])

        direction = None
        smc_context = ""

        if green_cross_up and latest['MACD'] > latest['MACD_signal'] and latest['RSI'] > 50:
            direction = "UP"
            smc_context = "[3MA Bullish Cross] "
        elif green_cross_down and latest['MACD'] < latest['MACD_signal'] and latest['RSI'] < 50:
            direction = "DOWN"
            smc_context = "[3MA Bearish Cross] "

        if not direction: 
            return {"status": "NO_SIGNAL", "price": round(latest['Close'], dec_places)}
            
        risk_dist = latest['ATR'] * 2.0
        sl = latest['Close'] - risk_dist if direction == "UP" else latest['Close'] + risk_dist
        tp1 = latest['Close'] + (risk_dist * 1.5) if direction == "UP" else latest['Close'] - (risk_dist * 1.5)
        
        return {
            "status": "SIGNAL_FOUND", "price": round(latest['Close'], dec_places), 
            "direction": direction, "strength": 85,
            "sl": round(sl, dec_places), 
            "tp_block": f"🎯 <b>Target 1:</b> <code>{round(tp1, dec_places)}</code>", 
            "context": smc_context
        }
    except:
        return {"status": "ERROR", "price": 0.0}

pairs_to_track = {"EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "USDJPY=X": "USDJPY", "XAUUSD=X": "XAUUSD"}

threading.Thread(target=run_fake_server, daemon=True).start()

while True:
    try:
        current_time = (datetime.utcnow() + timedelta(hours=6)).strftime("%I:%M %p")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        for ticker, display_name in pairs_to_track.items():
            time.sleep(2)
            result = generate_signal(ticker, display_name)
            if result["status"] == "SIGNAL_FOUND":
                msg = f"🔥 <b>Pair:</b> {display_name} | {result['direction']}\nContext: {result['context']}\nEntry: {result['price']}\nSL: {result['sl']}\n{result['tp_block']}"
                requests.post(url, json={"chat_id": FOREX_CHAT_ID, "text": msg, "parse_mode": "HTML"})
        
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(300)
