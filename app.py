import asyncio
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_VERSION = "v1.1.0 Real-time Webhook Ready"
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "CHANGE_ME_SECRET")
INITIAL_PRICE = float(os.getenv("INITIAL_XAUUSD_PRICE", "3343.10"))
ENABLE_SIMULATED_FEED = os.getenv("ENABLE_SIMULATED_FEED", "true").lower() == "true"
MAX_CANDLES = int(os.getenv("MAX_CANDLES", "800"))

app = FastAPI(title="Ray Gold Guardian Bot", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

class TVWebhookPayload(BaseModel):
    symbol: str = Field(default=SYMBOL)
    price: Optional[float] = None
    close: Optional[float] = None
    time: Optional[str] = None
    interval: Optional[str] = Field(default="M1")
    signal: Optional[str] = Field(default="TRADINGVIEW_ALERT")
    message: Optional[str] = Field(default="")
    secret: str

class RiskInput(BaseModel):
    balance: float = 300
    risk_percent: float = 1
    sl_points: float = 55

class CandleStore:
    def __init__(self, initial_price: float):
        self.price = initial_price
        self.last_signal = "WAIT"
        self.last_webhook = None
        self.candles: Dict[str, List[dict]] = {
            "M1": self._seed("M1", 1),
            "M5": self._seed("M5", 5),
            "M15": self._seed("M15", 15),
            "H1": self._seed("H1", 60),
        }

    def _seed(self, tf: str, minutes: int) -> List[dict]:
        now = int(time.time())
        base = self.price
        rows = []
        count = 180 if tf in ["M1", "M5"] else 120
        for i in range(count, 0, -1):
            t = now - i * minutes * 60
            drift = math.sin(i / 7) * 2.2 + random.uniform(-1.1, 1.1)
            open_p = base + drift + random.uniform(-0.8, 0.8)
            close_p = open_p + random.uniform(-1.8, 1.8)
            high_p = max(open_p, close_p) + random.uniform(0.3, 1.8)
            low_p = min(open_p, close_p) - random.uniform(0.3, 1.8)
            rows.append({
                "time": t,
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "volume": random.randint(80, 260),
            })
        return rows

    def update_tick(self, price: float, source: str = "simulated", signal: str = "TICK"):
        self.price = round(float(price), 2)
        now = int(time.time())
        for tf, minutes in [("M1", 1), ("M5", 5), ("M15", 15), ("H1", 60)]:
            bucket = now - (now % (minutes * 60))
            arr = self.candles[tf]
            if arr and arr[-1]["time"] == bucket:
                c = arr[-1]
                c["high"] = round(max(c["high"], self.price), 2)
                c["low"] = round(min(c["low"], self.price), 2)
                c["close"] = self.price
                c["volume"] = int(c.get("volume", 0)) + random.randint(1, 9)
            else:
                last_close = arr[-1]["close"] if arr else self.price
                arr.append({
                    "time": bucket,
                    "open": last_close,
                    "high": max(last_close, self.price),
                    "low": min(last_close, self.price),
                    "close": self.price,
                    "volume": random.randint(20, 120),
                })
                if len(arr) > MAX_CANDLES:
                    del arr[:-MAX_CANDLES]
        self.last_signal = signal
        self.last_webhook = {"source": source, "signal": signal, "price": self.price, "time": datetime.now(timezone.utc).isoformat()}

store = CandleStore(INITIAL_PRICE)
clients: Set[WebSocket] = set()

class Analyzer:
    @staticmethod
    def sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def atr(candles: List[dict], period: int = 14) -> float:
        if len(candles) < period + 1:
            return 0.0
        trs = []
        for i in range(-period, 0):
            c = candles[i]
            prev_close = candles[i - 1]["close"]
            tr = max(c["high"] - c["low"], abs(c["high"] - prev_close), abs(c["low"] - prev_close))
            trs.append(tr)
        return round(sum(trs) / len(trs), 2)

    @staticmethod
    def support_resistance(candles: List[dict], lookback: int = 48):
        recent = candles[-lookback:] if len(candles) >= lookback else candles
        resistance = round(max(c["high"] for c in recent), 2)
        support = round(min(c["low"] for c in recent), 2)
        return support, resistance

    @staticmethod
    def bias(candles: List[dict]) -> str:
        closes = [c["close"] for c in candles]
        fast = Analyzer.sma(closes, 20)
        slow = Analyzer.sma(closes, 50)
        if fast is None or slow is None:
            return "Neutral"
        if fast > slow:
            return "Bullish"
        if fast < slow:
            return "Bearish"
        return "Neutral"

    @staticmethod
    def analyze(balance: float = 300, risk_percent: float = 1, sl_points: float = 55) -> dict:
        m1 = store.candles["M1"]
        m5 = store.candles["M5"]
        m15 = store.candles["M15"]
        h1 = store.candles["H1"]
        price = store.price
        m5_support, m5_resistance = Analyzer.support_resistance(m5)
        h1_bias = Analyzer.bias(h1)
        m15_bias = Analyzer.bias(m15)
        m5_bias = Analyzer.bias(m5)
        atr = Analyzer.atr(m5)

        near_resistance = price >= m5_resistance - max(atr, 2.0)
        near_support = price <= m5_support + max(atr, 2.0)
        candle = m5[-1]
        rejection_down = candle["high"] - candle["close"] > max(1.2, atr * 0.35)
        rejection_up = candle["close"] - candle["low"] > max(1.2, atr * 0.35)

        action = "NO_TRADE"
        market_mode = "WAIT"
        condition = "รอราคาเข้าโซนชัดเจนและรอแท่ง M5 ยืนยัน"
        entry = None
        sl = None
        tp1 = None
        tp2 = None
        confidence = 50

        if h1_bias == "Bearish" and m15_bias in ["Bearish", "Neutral"]:
            market_mode = "SELL_RALLY"
            confidence += 12
            if near_resistance:
                confidence += 12
                condition = "ราคาเข้าใกล้โซนต้าน รอ M5 ปิดต่ำกว่าโซนหรือเกิด bearish rejection"
                if rejection_down or m5_bias == "Bearish":
                    action = "WAIT_CONFIRM_SELL"
                    confidence += 14
                    entry = round(price - 0.8, 2)
                    sl = round(m5_resistance + max(2.0, atr * 0.8), 2)
                    tp1 = round(price - max(5.0, atr * 1.5), 2)
                    tp2 = round(m5_support, 2)
        elif h1_bias == "Bullish" and m15_bias in ["Bullish", "Neutral"]:
            market_mode = "BUY_DIP"
            confidence += 12
            if near_support:
                confidence += 12
                condition = "ราคาเข้าใกล้โซนรับ รอ M5 ปิดเหนือโซนหรือเกิด bullish rejection"
                if rejection_up or m5_bias == "Bullish":
                    action = "WAIT_CONFIRM_BUY"
                    confidence += 14
                    entry = round(price + 0.8, 2)
                    sl = round(m5_support - max(2.0, atr * 0.8), 2)
                    tp1 = round(price + max(5.0, atr * 1.5), 2)
                    tp2 = round(m5_resistance, 2)
        else:
            market_mode = "RANGE_OR_MIXED"
            condition = "TF ใหญ่ยังขัดกัน ให้ลดขนาดไม้หรือรอ No Trade"

        risk_amount = balance * (risk_percent / 100)
        lot = max(0.01, min(0.2, risk_amount / max(sl_points, 1)))

        return {
            "symbol": SYMBOL,
            "version": APP_VERSION,
            "price": price,
            "market_mode": market_mode,
            "action": action,
            "condition": condition,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "confidence": min(95, max(30, int(confidence))),
            "risk": {
                "balance": balance,
                "risk_percent": risk_percent,
                "sl_points": sl_points,
                "risk_amount": round(risk_amount, 2),
                "suggested_lot": round(lot, 2),
                "daily_loss_limit_percent": 3,
                "max_trades_per_day": 3,
            },
            "levels": {
                "support": m5_support,
                "resistance": m5_resistance,
                "atr_m5": atr,
            },
            "timeframes": {
                "M1": Analyzer.bias(m1),
                "M5": m5_bias,
                "M15": m15_bias,
                "H1": h1_bias,
            },
            "last_webhook": store.last_webhook,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

async def broadcast(payload: dict):
    dead = []
    text = json.dumps(payload, ensure_ascii=False)
    for ws in list(clients):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)

@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "Ray Gold Guardian Bot",
        "version": APP_VERSION,
        "symbol": SYMBOL,
        "price": store.price,
        "simulated_feed": ENABLE_SIMULATED_FEED,
        "websocket_clients": len(clients),
        "time": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/xauusd/history")
def history(tf: str = "M1", limit: int = 300):
    tf = tf.upper()
    if tf not in store.candles:
        raise HTTPException(status_code=400, detail="Invalid timeframe. Use M1, M5, M15, H1")
    return {"symbol": SYMBOL, "tf": tf, "candles": store.candles[tf][-limit:]}

@app.get("/api/xauusd/analysis")
def analysis(balance: float = 300, risk_percent: float = 1, sl_points: float = 55):
    return Analyzer.analyze(balance=balance, risk_percent=risk_percent, sl_points=sl_points)

@app.post("/api/risk/lot")
def lot_calc(payload: RiskInput):
    risk_amount = payload.balance * (payload.risk_percent / 100)
    lot = max(0.01, min(0.2, risk_amount / max(payload.sl_points, 1)))
    return {"risk_amount": round(risk_amount, 2), "suggested_lot": round(lot, 2)}

@app.post("/api/tradingview/webhook")
async def tradingview_webhook(payload: TVWebhookPayload, request: Request):
    if payload.secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    price = payload.price if payload.price is not None else payload.close
    if price is None:
        raise HTTPException(status_code=400, detail="Missing price or close")
    store.update_tick(price=price, source="tradingview_webhook", signal=payload.signal or "TRADINGVIEW_ALERT")
    analysis_payload = Analyzer.analyze()
    event = {
        "type": "tradingview_webhook",
        "symbol": payload.symbol,
        "price": store.price,
        "interval": payload.interval,
        "signal": payload.signal,
        "message": payload.message,
        "analysis": analysis_payload,
        "time": datetime.now(timezone.utc).isoformat(),
    }
    await broadcast(event)
    return {"ok": True, "received": event}

@app.websocket("/ws/xauusd")
async def websocket_xauusd(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "snapshot", "analysis": Analyzer.analyze(), "price": store.price}, ensure_ascii=False))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients.discard(ws)
    except Exception:
        clients.discard(ws)

@app.on_event("startup")
async def startup_event():
    async def feed_loop():
        while True:
            await asyncio.sleep(2)
            if ENABLE_SIMULATED_FEED:
                drift = random.uniform(-0.8, 0.8)
                store.update_tick(store.price + drift, source="simulated_feed", signal="SIM_TICK")
                await broadcast({"type": "tick", "price": store.price, "analysis": Analyzer.analyze(), "time": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(feed_loop())
