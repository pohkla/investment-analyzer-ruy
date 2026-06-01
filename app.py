import asyncio
import base64
import json
import math
import os
import random
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_VERSION = "v1.4 Vision AI Chart Analysis"
SYMBOL = os.getenv("SYMBOL", "XAUUSD")
WEBHOOK_SECRET = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "CHANGE_ME_SECRET")
INITIAL_PRICE = float(os.getenv("INITIAL_XAUUSD_PRICE", "4540.00"))
ENABLE_SIMULATED_FEED = os.getenv("ENABLE_SIMULATED_FEED", "false").lower() == "true"
MAX_CANDLES = int(os.getenv("MAX_CANDLES", "800"))
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_IMAGE_UPLOAD_MB = int(os.getenv("MAX_IMAGE_UPLOAD_MB", "8"))

# Vision AI settings
# Set OPENAI_API_KEY on Render to enable direct chart-image reading.
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "openai").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

# Live feed settings
# LIVE_PRICE_PROVIDER options: none | twelvedata | goldapi
LIVE_PRICE_PROVIDER = os.getenv("LIVE_PRICE_PROVIDER", "none").lower()
LIVE_POLL_SECONDS = max(2, int(os.getenv("LIVE_POLL_SECONDS", "5")))
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
TWELVEDATA_SYMBOL = os.getenv("TWELVEDATA_SYMBOL", "XAU/USD")
GOLDAPI_KEY = os.getenv("GOLDAPI_KEY", "")
GOLDAPI_SYMBOL = os.getenv("GOLDAPI_SYMBOL", "XAU")
GOLDAPI_CURRENCY = os.getenv("GOLDAPI_CURRENCY", "USD")

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
        self.last_live_feed = None
        self.last_chart_image = None
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

    def update_tick(self, price: float, source: str = "manual", signal: str = "TICK"):
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
                    "high": round(max(last_close, self.price), 2),
                    "low": round(min(last_close, self.price), 2),
                    "close": self.price,
                    "volume": random.randint(20, 120),
                })
                if len(arr) > MAX_CANDLES:
                    del arr[:-MAX_CANDLES]
        self.last_signal = signal
        payload = {"source": source, "signal": signal, "price": self.price, "time": datetime.now(timezone.utc).isoformat()}
        if source == "tradingview_webhook":
            self.last_webhook = payload
        else:
            self.last_live_feed = payload

store = CandleStore(INITIAL_PRICE)
clients: Set[WebSocket] = set()

class LivePriceClient:
    @staticmethod
    async def fetch_twelvedata_price() -> Tuple[float, dict]:
        if not TWELVEDATA_API_KEY:
            raise RuntimeError("Missing TWELVEDATA_API_KEY")
        url = "https://api.twelvedata.com/price"
        params = {"symbol": TWELVEDATA_SYMBOL, "apikey": TWELVEDATA_API_KEY}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            data = r.json()
        if "price" not in data:
            raise RuntimeError(f"Twelve Data response missing price: {data}")
        return float(data["price"]), data

    @staticmethod
    async def fetch_goldapi_price() -> Tuple[float, dict]:
        if not GOLDAPI_KEY:
            raise RuntimeError("Missing GOLDAPI_KEY")
        url = f"https://www.goldapi.io/api/{GOLDAPI_SYMBOL}/{GOLDAPI_CURRENCY}"
        headers = {"x-access-token": GOLDAPI_KEY, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers)
            data = r.json()
        # GoldAPI commonly returns price, ask, bid fields depending on plan/endpoint.
        raw_price = data.get("price") or data.get("ask") or data.get("bid")
        if raw_price is None:
            raise RuntimeError(f"GoldAPI response missing price: {data}")
        return float(raw_price), data

    @staticmethod
    async def fetch_price() -> Tuple[float, dict]:
        if LIVE_PRICE_PROVIDER == "twelvedata":
            return await LivePriceClient.fetch_twelvedata_price()
        if LIVE_PRICE_PROVIDER == "goldapi":
            return await LivePriceClient.fetch_goldapi_price()
        raise RuntimeError("LIVE_PRICE_PROVIDER is none")

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
            "feed": {
                "provider": LIVE_PRICE_PROVIDER,
                "simulated_feed": ENABLE_SIMULATED_FEED,
                "last_live_feed": store.last_live_feed,
                "last_webhook": store.last_webhook,
        "last_chart_image": store.last_chart_image,
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }



class VisionAnalyzer:
    @staticmethod
    def _extract_json(text: str) -> dict:
        """Best-effort JSON extraction from model output."""
        if not text:
            return {}
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            return json.loads(cleaned)
        except Exception:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except Exception:
                    pass
        return {"raw_text": text}

    @staticmethod
    async def analyze_image(image_payload: dict, numeric_analysis: dict) -> dict:
        """Analyze the uploaded chart image with Vision AI when OPENAI_API_KEY is available.

        If no key is configured, return a safe fallback so the app still works on Render.
        """
        filename = image_payload.get("filename")
        content_type = image_payload.get("content_type") or "image/png"
        image_path = UPLOAD_DIR / filename if filename else None

        fallback = {
            "enabled": False,
            "provider": VISION_PROVIDER,
            "model": OPENAI_VISION_MODEL,
            "summary": "ยังไม่ได้เปิด Vision AI เพราะยังไม่ได้ตั้งค่า OPENAI_API_KEY ใน Render",
            "observations": [
                "ระบบใช้ภาพเป็นบริบทแล้ว แต่ยังไม่ได้อ่านแท่งเทียน/EMA/RSI จากภาพโดยตรง",
                "เพิ่ม OPENAI_API_KEY เพื่อให้ระบบอ่านข้อความจากภาพและวิเคราะห์ภาพกราฟจริง"
            ],
            "chart_bias": "UNKNOWN",
            "key_levels_from_image": [],
            "trade_action": numeric_analysis.get("action", "NO_TRADE"),
            "confidence_adjustment": 0,
            "risk_notes": ["ห้ามเข้าไม้จากภาพอย่างเดียว ต้องรอ confirmation และคุม risk ตามระบบ"],
            "raw_text": None,
        }

        if not OPENAI_API_KEY:
            return fallback
        if not image_path or not image_path.exists():
            fallback["summary"] = "ไม่พบไฟล์ภาพล่าสุดบนเซิร์ฟเวอร์ กรุณาอัปโหลดหรือวางภาพใหม่"
            return fallback

        raw = image_path.read_bytes()
        b64 = base64.b64encode(raw).decode("utf-8")
        data_url = f"data:{content_type};base64,{b64}"

        system_prompt = (
            "You are Ray Gold Guardian Bot, an expert XAUUSD chart analyst. "
            "Analyze the uploaded trading chart image. Be conservative. "
            "Do not claim certainty. Return ONLY valid JSON in Thai language."
        )
        user_text = {
            "task": "วิเคราะห์ภาพกราฟ XAUUSD จากรูปภาพจริง แล้วใช้ร่วมกับ numeric_analysis ของระบบ",
            "numeric_analysis": numeric_analysis,
            "required_json_schema": {
                "summary": "สรุปภาพรวมจากภาพ 1-2 ประโยค",
                "observations": ["สิ่งที่เห็นจากภาพ เช่น trend, EMA, RSI, candle structure"],
                "chart_bias": "BULLISH | BEARISH | RANGE | MIXED | UNKNOWN",
                "key_levels_from_image": [
                    {"level": 0, "type": "support/resistance/supply/demand", "reason": "เหตุผลจากภาพ"}
                ],
                "trade_action": "NO_TRADE | WAIT_CONFIRM_BUY | WAIT_CONFIRM_SELL | BUY_READY | SELL_READY",
                "entry_plan": {"entry": None, "sl": None, "tp1": None, "tp2": None},
                "confirmation_needed": ["เงื่อนไขที่ต้องรอก่อนเข้า"],
                "risk_notes": ["ข้อควรระวัง"],
                "confidence_adjustment": 0
            }
        }

        body = {
            "model": OPENAI_VISION_MODEL,
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json.dumps(user_text, ensure_ascii=False)},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ]
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            if r.status_code >= 400:
                return {
                    **fallback,
                    "enabled": False,
                    "summary": f"Vision AI เรียกใช้งานไม่สำเร็จ: HTTP {r.status_code}",
                    "raw_text": r.text[:800],
                }
            data = r.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = VisionAnalyzer._extract_json(content)
        if not isinstance(parsed, dict):
            parsed = {"raw_text": content}

        return {
            "enabled": True,
            "provider": VISION_PROVIDER,
            "model": OPENAI_VISION_MODEL,
            "summary": parsed.get("summary") or "Vision AI วิเคราะห์ภาพแล้ว แต่ไม่ได้ส่ง summary กลับมา",
            "observations": parsed.get("observations") or [],
            "chart_bias": parsed.get("chart_bias") or "UNKNOWN",
            "key_levels_from_image": parsed.get("key_levels_from_image") or [],
            "trade_action": parsed.get("trade_action") or numeric_analysis.get("action", "NO_TRADE"),
            "entry_plan": parsed.get("entry_plan") or {},
            "confirmation_needed": parsed.get("confirmation_needed") or [],
            "risk_notes": parsed.get("risk_notes") or [],
            "confidence_adjustment": int(parsed.get("confidence_adjustment") or 0),
            "raw_text": content,
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
        "live_price_provider": LIVE_PRICE_PROVIDER,
        "simulated_feed": ENABLE_SIMULATED_FEED,
        "websocket_clients": len(clients),
        "last_live_feed": store.last_live_feed,
        "last_webhook": store.last_webhook,
        "last_chart_image": store.last_chart_image,
        "time": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/xauusd/live-price")
async def live_price():
    price, raw = await LivePriceClient.fetch_price()
    store.update_tick(price=price, source=LIVE_PRICE_PROVIDER, signal="LIVE_PRICE_MANUAL_FETCH")
    await broadcast({"type": "tick", "price": store.price, "analysis": Analyzer.analyze(), "source": LIVE_PRICE_PROVIDER, "time": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "provider": LIVE_PRICE_PROVIDER, "price": store.price, "raw": raw}

@app.get("/api/xauusd/history")
def history(tf: str = "M1", limit: int = 300):
    tf = tf.upper()
    if tf not in store.candles:
        raise HTTPException(status_code=400, detail="Invalid timeframe. Use M1, M5, M15, H1")
    return {"symbol": SYMBOL, "tf": tf, "candles": store.candles[tf][-limit:]}

@app.get("/api/xauusd/analysis")
def analysis(balance: float = 300, risk_percent: float = 1, sl_points: float = 55):
    return Analyzer.analyze(balance=balance, risk_percent=risk_percent, sl_points=sl_points)


@app.post("/api/chart-image/upload")
async def upload_chart_image(file: UploadFile = File(...), note: str = Form(default="")):
    allowed = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ PNG, JPG/JPEG หรือ WEBP")

    raw = await file.read()
    max_bytes = MAX_IMAGE_UPLOAD_MB * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"ไฟล์ใหญ่เกิน {MAX_IMAGE_UPLOAD_MB}MB")

    suffix = allowed[file.content_type]
    safe_name = f"chart-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}{suffix}"
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(raw)

    image_url = f"/static/uploads/{safe_name}"
    payload = {
        "ok": True,
        "status": "ได้รับภาพกราฟแล้ว",
        "filename": safe_name,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(raw),
        "image_url": image_url,
        "note": note,
        "summary": "ระบบได้รับภาพกราฟเรียบร้อยแล้ว ภาพนี้สามารถใช้ประกอบการวิเคราะห์ร่วมกับราคาจริง, Timeframe, Support/Resistance และ Risk Guard ได้",
        "analysis_hint": {
            "action": "IMAGE_READY",
            "condition": "ตรวจภาพกราฟร่วมกับข้อมูล Real-time ก่อนออก Signal; หากต้องการ Vision AI จริง ให้ต่อ OpenAI Vision/โมเดลภาพในขั้นถัดไป",
            "next_step": "ใช้ปุ่ม Analyze เพื่อดึง Trade Plan ล่าสุด หรือเชื่อม Vision API เพื่ออ่านโครงสร้างจากรูปภาพอัตโนมัติ"
        },
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    store.last_chart_image = payload
    await broadcast({"type": "chart_image_uploaded", **payload})
    return payload


@app.post("/api/chart-image/analyze")
async def analyze_chart_image(balance: float = 300, risk_percent: float = 1, sl_points: float = 55):
    if not store.last_chart_image:
        raise HTTPException(status_code=400, detail="ยังไม่มีภาพกราฟ กรุณาอัปโหลดหรือวางภาพก่อน")

    analysis_payload = Analyzer.analyze(balance=balance, risk_percent=risk_percent, sl_points=sl_points)
    image_payload = store.last_chart_image
    vision = await VisionAnalyzer.analyze_image(image_payload, analysis_payload)

    adjusted_confidence = analysis_payload.get("confidence", 50) + int(vision.get("confidence_adjustment") or 0)
    analysis_payload["confidence"] = min(95, max(30, adjusted_confidence))
    if vision.get("trade_action") and vision.get("trade_action") != "UNKNOWN":
        analysis_payload["action"] = vision.get("trade_action")

    image_analysis = {
        "title": "Vision AI วิเคราะห์ภาพกราฟแล้ว" if vision.get("enabled") else "วิเคราะห์ภาพกราฟแบบ Context แล้ว",
        "action": analysis_payload.get("action", "NO_TRADE"),
        "condition": "; ".join(vision.get("confirmation_needed") or []) or analysis_payload.get("condition") or "รอ confirmation ก่อนเข้าไม้",
        "summary": vision.get("summary") or f"ภาพล่าสุด: {image_payload.get('original_filename') or image_payload.get('filename')} • ราคา: {analysis_payload.get('price')} • Mode: {analysis_payload.get('market_mode')} • Confidence: {analysis_payload.get('confidence')}/100",
        "observations": vision.get("observations") or [],
        "chart_bias": vision.get("chart_bias", "UNKNOWN"),
        "key_levels_from_image": vision.get("key_levels_from_image") or [],
        "risk_notes": vision.get("risk_notes") or [],
        "vision_enabled": vision.get("enabled", False),
    }
    result = {
        "ok": True,
        "image": image_payload,
        "analysis": analysis_payload,
        "image_analysis": image_analysis,
        "vision": vision,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    await broadcast({"type": "chart_image_analyzed", **result})
    return result

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
        last_error = None
        while True:
            await asyncio.sleep(LIVE_POLL_SECONDS)
            if LIVE_PRICE_PROVIDER in {"twelvedata", "goldapi"}:
                try:
                    price, raw = await LivePriceClient.fetch_price()
                    store.update_tick(price, source=LIVE_PRICE_PROVIDER, signal="LIVE_PRICE_TICK")
                    await broadcast({"type": "tick", "price": store.price, "analysis": Analyzer.analyze(), "source": LIVE_PRICE_PROVIDER, "time": datetime.now(timezone.utc).isoformat()})
                    last_error = None
                    continue
                except Exception as exc:
                    last_error = str(exc)
                    store.last_live_feed = {"source": LIVE_PRICE_PROVIDER, "error": last_error, "time": datetime.now(timezone.utc).isoformat()}
                    await broadcast({"type": "feed_error", "error": last_error, "source": LIVE_PRICE_PROVIDER, "time": datetime.now(timezone.utc).isoformat()})
            if ENABLE_SIMULATED_FEED:
                drift = random.uniform(-0.8, 0.8)
                store.update_tick(store.price + drift, source="simulated_feed", signal="SIM_TICK")
                await broadcast({"type": "tick", "price": store.price, "analysis": Analyzer.analyze(), "source": "simulated_feed", "time": datetime.now(timezone.utc).isoformat()})
    asyncio.create_task(feed_loop())
