import requests
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# আপনার ভেরিফাইড তথ্যসমূহ
BOT_TOKEN = "8264008675:AAEHzakAXPZeNVZKWlvYHRWboyjAuUhg0QM"
FOREX_CHAT_ID = "-1004319798911"  

class DummyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Kanak Institutional Ultra-Filtered Engine Live!")
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

# টেকনিক্যাল ইন্ডিকেটর ফাংশনসমূহ
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

def generate_signals_for_all_strategies(ticker_symbol, display_name):
    signals_list = []
    try:
        df_5m = fetch_candles(ticker_symbol, "5m", "5d")
        df_1h = fetch_candles(ticker_symbol, "1h", "1mo")
        
        if df_5m is None or len(df_5m) < 100 or df_1h is None or len(df_1h) < 50:
            return signals_list

        is_jpy = "JPY" in ticker_symbol
        dec_places = 2 if is_jpy else 4
        
        latest = df_5m.iloc[-1]
        prev = df_5m.iloc[-2]
        prev2 = df_5m.iloc[-3]
        price = latest['Close']
        
        atr_val = calculate_atr(df_5m).iloc[-1]
        current_candle_size = latest['High'] - latest['Low']
        if current_candle_size > (atr_val * 3.5): 
            return signals_list

        df_1h['EMA_200'] = calculate_ema(df_1h['Close'], 200)
        htf_trend = "STRONG_BUY" if df_1h['Close'].iloc[-1] > df_1h['EMA_200'].iloc[-1] else "STRONG_SELL"

        df_5m['CMF'] = calculate_cmf(df_5m, 20)
        volume_flow = df_5m['CMF'].iloc[-1]

        support_level = df_5m['Low'].rolling(window=25).min().iloc[-1]
        resistance_level = df_5m['High'].rolling(window=25).max().iloc[-1]
        buffer = atr_val * 0.3

        def create_adaptive_tp_sl_block(direction_type, entry_p):
            if direction_type == "UP":
                sl_val = min(support_level - buffer, entry_p - (atr_val * 1.5))
                risk_unit = entry_p - sl_val
                tp1_val = entry_p + (risk_unit * 2.0)
                tp2_val = entry_p + (risk_unit * 3.0)
                tp3_val = entry_p + (risk_unit * 4.0)
                tp4_val = entry_p + (risk_unit * 5.0)
            else:
                sl_val = max(resistance_level + buffer, entry_p + (atr_val * 1.5))
                risk_unit = sl_val - entry_p
                tp1_val = entry_p - (risk_unit * 2.0)
                tp2_val = entry_p - (risk_unit * 3.0)
                tp3_val = entry_p - (risk_unit * 4.0)
                tp4_val = entry_p - (risk_unit * 5.0)
                
            return round(sl_val, dec_places), (
                f"🎯 <b>TP1 (1:2 RR):</b> <code>{round(tp1_val, dec_places)}</code>\n"
                f"🎯 <b>TP2 (1:3 RR):</b> <code>{round(tp2_val, dec_places)}</code>\n"
                f"🎯 <b>TP3 (1:4 RR):</b> <code>{round(tp3_val, dec_places)}</code>\n"
                f"🎯 <b>TP4 (1:5 RR):</b> <code>{round(tp4_val, dec_places)}</code>"
            )

        # =========================================================================
        # 🔵 STRATEGY 1: BOLLINGER BANDS REVERSAL
        # =========================================================================
        if prev['Close'] <= bb_lower.iloc[-2] and price > bb_lower.iloc[-1] and rsi_vals.iloc[-1] > 35:
            if htf_trend == "STRONG_BUY" and volume_flow > -0.05:
                sl, tp_b = create_adaptive_tp_sl_block("UP", price)
                signals_list.append({"strategy": "Bollinger Bands Reversal 🔵", "direction": "🟢 BUY", "context": "Price Pierced Lower Band & Reversing Upwards", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})
        elif prev['Close'] >= bb_upper.iloc[-2] and price < bb_upper.iloc[-1] and rsi_vals.iloc[-1] < 65:
            if htf_trend == "STRONG_SELL" and volume_flow < 0.05:
                sl, tp_b = create_adaptive_tp_sl_block("DOWN", price)
                signals_list.append({"strategy": "Bollinger Bands Reversal 🔵", "direction": "🔴 SELL", "context": "Price Pierced Upper Band & Reversing Downwards", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})

        # =========================================================================
        # 📊 STRATEGY 2: MACD MOMENTUM CROSSOVER
        # =========================================================================
        if macd_line.iloc[-2] <= macd_signal.iloc[-2] and macd_line.iloc[-1] > macd_signal.iloc[-1]:
            if htf_trend == "STRONG_BUY" and volume_flow > 0.02:
                sl, tp_b = create_adaptive_tp_sl_block("UP", price)
                signals_list.append({"strategy": "MACD Momentum Flow 📊", "direction": "🟢 BUY", "context": "MACD Bullish Crossover confirmed with High Volume", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})
        elif macd_line.iloc[-2] >= macd_signal.iloc[-2] and macd_line.iloc[-1] < macd_signal.iloc[-1]:
            if htf_trend == "STRONG_SELL" and volume_flow < -0.02:
                sl, tp_b = create_adaptive_tp_sl_block("DOWN", price)
                signals_list.append({"strategy": "MACD Momentum Flow 📊", "direction": "🔴 SELL", "context": "MACD Bearish Crossover confirmed with High Volume", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})

        # =========================================================================
        # ⚡ STRATEGY 3: ICT FAIR VALUE GAP (FVG SNIPER)
        # =========================================================================
        if prev2['High'] < latest['Low'] and rsi_vals.iloc[-1] > 50:
            if htf_trend == "STRONG_BUY" and volume_flow > 0.0:
                sl, tp_b = create_adaptive_tp_sl_block("UP", price)
                signals_list.append({"strategy": "ICT FVG Sniper ⚡", "direction": "🟢 BUY", "context": "Bullish Fair Value Gap Aligned with 1H Macro Trend", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})
        elif prev2['Low'] > latest['High'] and rsi_vals.iloc[-1] < 50:
            if htf_trend == "STRONG_SELL" and volume_flow < 0.0:
                sl, tp_b = create_adaptive_tp_sl_block("DOWN", price)
                signals_list.append({"strategy": "ICT FVG Sniper ⚡", "direction": "🔴 SELL", "context": "Bearish Fair Value Gap Aligned with 1H Macro Trend", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})

        # =========================================================================
        # 🏛️ STRATEGY 4: SMART MONEY CONCEPTS (SMC MATRIX)
        # =========================================================================
        if htf_trend == "STRONG_BUY" and price <= (support_level + (atr_val * 0.4)) and volume_flow > -0.02:
            sl, tp_b = create_adaptive_tp_sl_block("UP", price)
            signals_list.append({"strategy": "SMC Matrix Setup 🏛️", "direction": "🟢 BUY", "context": "SMC Demand Liquidity Sweep matching HTF Bullish Orderflow", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})
        elif htf_trend == "STRONG_SELL" and price >= (resistance_level - (atr_val * 0.4)) and volume_flow < 0.02:
            sl, tp_b = create_adaptive_tp_sl_block("DOWN", price)
            signals_list.append({"strategy": "SMC Matrix Setup 🏛️", "direction": "🔴 SELL", "context": "SMC Supply Block Rejection matching HTF Bearish Orderflow", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})

        # =========================================================================
        # 📈 STRATEGY 5: 3MA CROSSING ENGINE
        # =========================================================================
        df_5m['EMA_Green'] = calculate_ema(df_5m['Close'], 12)
        df_5m['EMA_Yellow'] = calculate_ema(df_5m['Close'], 26)
        
        g_cross_up = (df_5m['EMA_Green'].iloc[-2] <= df_5m['EMA_Yellow'].iloc[-2]) and (df_5m['EMA_Green'].iloc[-1] > df_5m['EMA_Yellow'].iloc[-1])
        g_cross_down = (df_5m['EMA_Green'].iloc[-2] >= df_5m['EMA_Yellow'].iloc[-2]) and (df_5m['EMA_Green'].iloc[-1] < df_5m['EMA_Yellow'].iloc[-1])

        if g_cross_up and rsi_vals.iloc[-1] > 50 and htf_trend == "STRONG_BUY":
            sl, tp_b = create_adaptive_tp_sl_block("UP", price)
            signals_list.append({"strategy": "3MA Trend Cross 📈", "direction": "🟢 BUY", "context": "3MA Golden Cross Aligned with High Timeframe Trend", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})
        elif g_cross_down and rsi_vals.iloc[-1] < 48 and htf_trend == "STRONG_SELL":
            sl, tp_b = create_adaptive_tp_sl_block("DOWN", price)
            signals_list.append({"strategy": "3MA Trend Cross 📈", "direction": "🔴 SELL", "context": "3MA Death Cross Aligned with High Timeframe Trend", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})

        # =========================================================================
        # 🕯️ STRATEGY 6: PRICE ACTION CANDLESTICK PATTERN
        # =========================================================================
        is_prev_red = prev['Close'] < prev['Open']
        is_prev_green = prev['Close'] > prev['Open']
        is_latest_green = latest['Close'] > latest['Open']
        is_latest_red = latest['Close'] < latest['Open']

        bullish_engulfing = is_prev_red and is_latest_green and (latest['Close'] > prev['Open']) and (latest['Open'] < prev['Close'])
        bearish_engulfing = is_prev_green and is_latest_red and (latest['Close'] < prev['Open']) and (latest['Open'] > prev['Close'])

        if bullish_engulfing and htf_trend == "STRONG_BUY" and volume_flow > 0.01:
            sl, tp_b = create_adaptive_tp_sl_block("UP", price)
            signals_list.append({"strategy": "Price Action Candle 🕯️", "direction": "🟢 BUY", "context": "Institutional Bullish Engulfing Candlestick Reversal", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})
        elif bearish_engulfing and htf_trend == "STRONG_SELL" and volume_flow < -0.01:
            sl, tp_b = create_adaptive_tp_sl_block("DOWN", price)
            signals_list.append({"strategy": "Price Action Candle 🕯️", "direction": "🔴 SELL", "context": "Institutional Bearish Engulfing Candlestick Reversal", "price": round(price, dec_places), "sl": sl, "tp_block": tp_b})

    except Exception as e:
        print(f"Strategy Scan Error: {e}")
        
    return signals_list

pairs_to_track = {
    "EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "USDJPY=X": "USDJPY", "USDCHF=X": "USDCHF",
    "AUDUSD=X": "AUDUSD", "USDCAD=X": "USDCAD", "NZDUSD=X": "NZDUSD", "XAUUSD=X": "XAUUSD"
}

# ফেক সার্ভার ব্যাকগ্রাউন্ডে চালু করা
threading.Thread(target=run_fake_server, daemon=True).start()

# =========================================================================
# 🚀 BOT STARTUP TELEGRAM NOTIFICATION SYSTEM
# =========================================================================
try:
    startup_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    bst_now = datetime.utcnow() + timedelta(hours=6)
    startup_time = bst_now.strftime("%I:%M:%Y %p")
    sessions_active = get_current_forex_sessions()
    
    startup_message = (
        f"🚀 <b>Kanak Institutional Matrix Live!</b>\n"
        f"───────────────────\n"
        f"✅ <b>Status:</b> Bot Started & Scanning Markets...\n"
        f"🛡️ <b>Filters Active:</b> HTF 1H Trend + CMF Volume + S/R Adaptive\n"
        f"📊 <b>Pairs Loaded:</b> 8 Major Forex Currencies\n\n"
        f"⏱️ <i>Startup BST: {startup_time}</i>\n"
        f"🌐 <i>Active Sessions: {sessions_active}</i>\n"
        f"───────────────────\n"
        f"📌 <i>Now watching for high-accuracy algorithmic entries!</i>"
    )
    requests.post(startup_url, json={"chat_id": FOREX_CHAT_ID, "text": startup_message, "parse_mode": "HTML"}, timeout=10)
    print("📢 Startup notification successfully pushed to Telegram!")
except Exception as startup_err:
    print(f"Failed to send startup alert: {startup_err}")

# ⏱️ ৫ মিনিটের মেইন লুপ
while True:
    try:
        current_session = get_current_forex_sessions()
        now_bst = datetime.utcnow() + timedelta(hours=6)
        current_time = now_bst.strftime("%I:%M %p")
        
        print(f"\n🔄 SCANNING CHARTS VIA ADAPTIVE FILTER MATRIX AT {current_time}")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        for ticker, display_name in pairs_to_track.items():
            time.sleep(1.5)
            detected_signals = generate_signals_for_all_strategies(ticker, display_name)
            
            for sig in detected_signals:
                forex_message = (
                    f"🔥 <b>{sig['strategy']}</b>\n"
                    f"───────────────────\n"
                    f"📊 <b>Pair:</b> <code>{display_name}</code> → <b>{sig['direction']}</b>\n"
                    f"🛡️ <b>Strategy Context:</b> <i>{sig['context']}</i>\n\n"
                    f"💵 <b>Entry Price:</b> <code>{sig['price']}</code>\n"
                    f"🛑 <b>Adaptive SL (S/R Base):</b> <code>{sig['sl']}</code>\n"
                    f"───────────────────\n"
                    f"{sig['tp_block']}\n\n"
                    f"⏱ <i>Time: {current_time} | Session: {current_session}</i>\n"
                    f"#{display_name} #{sig['strategy'].split()[0]} #ForexSniper"
                )
                
                requests.post(url, json={"chat_id": FOREX_CHAT_ID, "text": forex_message, "parse_mode": "HTML"}, timeout=10)
                print(f"   🎯 Adaptive Signal Pushed: {display_name} via {sig['strategy']}")
                time.sleep(1.0)
                
    except Exception as e:
        print(f"Loop error: {e}")
        
    time.sleep(300)
