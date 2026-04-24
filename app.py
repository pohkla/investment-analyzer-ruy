from __future__ import annotations

import io
import json
import math
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image

app = FastAPI(
    title="Ray AI Trader",
    version="1.0.0",
    description="Prototype chart image and OHLC CSV analyzer for trading dashboards.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OCR_AVAILABLE = False
OCR_ERROR = ""
try:
    import pytesseract  # type: ignore

    OCR_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on system package
    pytesseract = None  # type: ignore
    OCR_ERROR = str(exc)

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
REQUIRED_CSV_COLUMNS = {"time", "open", "high", "low", "close"}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def read_image_upload(file_bytes: bytes) -> np.ndarray:
    try:
        pil_image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc


def extract_ocr_text(image_bgr: np.ndarray) -> Dict[str, Any]:
    if not OCR_AVAILABLE or pytesseract is None:
        return {
            "available": False,
            "text": "",
            "error": OCR_ERROR or "pytesseract is not installed or tesseract binary is unavailable",
        }

    try:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        gray = cv2.bilateralFilter(gray, 5, 75, 75)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(thresh, config="--psm 6")
        return {"available": True, "text": text.strip(), "error": ""}
    except Exception as exc:
        return {"available": False, "text": "", "error": f"OCR failed: {exc}"}


def detect_metadata(ocr_text: str) -> Dict[str, Any]:
    normalized = (ocr_text or "").upper().replace("/", "")
    symbol_patterns = [
        r"\bXAUUSD\b", r"\bBTCUSD\b", r"\bETHUSD\b", r"\bNAS100\b", r"\bUS30\b",
        r"\bSPX500\b", r"\bGER40\b", r"\bUSDJPY\b", r"\bEURUSD\b", r"\bGBPUSD\b",
        r"\b[A-Z]{2,6}USD\b", r"\b[A-Z]{1,5}\b",
    ]
    timeframe_patterns = [r"\bM1\b", r"\bM5\b", r"\bM15\b", r"\bM30\b", r"\bH1\b", r"\bH4\b", r"\bD1\b", r"\bW1\b"]

    symbol = "Unknown"
    for pattern in symbol_patterns:
        match = re.search(pattern, normalized)
        if match:
            candidate = match.group(0)
            if candidate not in {"BUY", "SELL", "WAIT", "OPEN", "HIGH", "LOW", "CLOSE", "TIME"}:
                symbol = candidate
                break

    timeframe = "Unknown"
    for pattern in timeframe_patterns:
        match = re.search(pattern, normalized)
        if match:
            timeframe = match.group(0)
            break

    prices = []
    for raw in re.findall(r"\b\d{1,6}(?:[,.]\d{1,5})?\b", normalized):
        value = safe_float(raw.replace(",", ""))
        if value and value > 0:
            prices.append(value)

    current_price = None
    if prices:
        filtered = [p for p in prices if 0.0001 < p < 1_000_000]
        current_price = filtered[-1] if filtered else prices[-1]

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "detected_prices": prices[:30],
        "current_price": current_price,
    }


def find_price_path(image_bgr: np.ndarray) -> Dict[str, Any]:
    height, width = image_bgr.shape[:2]
    crop = image_bgr[int(height * 0.08): int(height * 0.92), int(width * 0.03): int(width * 0.97)]
    if crop.size == 0:
        crop = image_bgr
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 150)

    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)

    col_points = []
    h, w = edges.shape
    for x in range(w):
        ys = np.where(edges[:, x] > 0)[0]
        if len(ys) > 0:
            # Favor the right-side visible price structure by using median edge location per column.
            col_points.append((x, float(np.median(ys))))

    if len(col_points) < max(20, w * 0.08):
        # Fallback: use intensity changes as proxy for chart strokes.
        sobel = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        abs_sobel = np.abs(sobel)
        for x in range(w):
            ys = np.where(abs_sobel[:, x] > np.percentile(abs_sobel, 93))[0]
            if len(ys) > 0:
                col_points.append((x, float(np.median(ys))))

    if not col_points:
        return {"path": [], "width": w, "height": h}

    xs = np.array([p[0] for p in col_points], dtype=float)
    ys = np.array([p[1] for p in col_points], dtype=float)

    # Interpolate missing columns and smooth.
    full_x = np.arange(0, w)
    full_y = np.interp(full_x, xs, ys)
    if len(full_y) >= 9:
        kernel_size = max(5, min(31, (len(full_y) // 25) * 2 + 1))
        full_y = cv2.GaussianBlur(full_y.reshape(1, -1).astype(np.float32), (kernel_size, 1), 0).flatten()

    return {"path": full_y.tolist(), "width": w, "height": h}


def detect_swings(path: List[float], min_distance: int = 12) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    if len(path) < min_distance * 3:
        return [], []
    arr = np.array(path, dtype=float)
    highs = []  # visually high price = smaller y value
    lows = []   # visually low price = larger y value
    window = max(5, min_distance)
    for i in range(window, len(arr) - window):
        segment = arr[i - window:i + window + 1]
        if arr[i] == np.min(segment):
            highs.append({"x": float(i), "y": float(arr[i])})
        if arr[i] == np.max(segment):
            lows.append({"x": float(i), "y": float(arr[i])})
    # Reduce clusters.
    def reduce(points: List[Dict[str, float]]) -> List[Dict[str, float]]:
        reduced = []
        for point in points:
            if not reduced or point["x"] - reduced[-1]["x"] >= min_distance:
                reduced.append(point)
            else:
                # keep more extreme point in the cluster
                prev = reduced[-1]
                if abs(point["y"] - np.mean(arr)) > abs(prev["y"] - np.mean(arr)):
                    reduced[-1] = point
        return reduced[-10:]
    return reduce(highs), reduce(lows)


def image_chart_analysis(image_bgr: np.ndarray, metadata: Dict[str, Any]) -> Dict[str, Any]:
    path_info = find_price_path(image_bgr)
    path = path_info.get("path", [])
    h = float(path_info.get("height", 1) or 1)

    if len(path) < 20:
        return {
            "trend": "Unknown",
            "bias": "Neutral",
            "confidence": 25,
            "volatility": "Unknown",
            "support_resistance": {"support_visual": [], "resistance_visual": []},
            "swing_highs": [],
            "swing_lows": [],
            "breakout": "Insufficient visual data",
            "liquidity_zones": [],
            "candlestick_read": "Could not detect enough chart structure from image.",
        }

    arr_y = np.array(path, dtype=float)
    # In image space: y decreases = price up. Convert to visual price score.
    price_proxy = h - arr_y
    x = np.arange(len(price_proxy), dtype=float)
    slope = np.polyfit(x, price_proxy, 1)[0]
    net_move = price_proxy[-1] - price_proxy[0]
    price_range = max(1.0, float(np.max(price_proxy) - np.min(price_proxy)))
    normalized_slope = slope * len(price_proxy) / price_range
    normalized_net = net_move / price_range

    rolling_std = float(pd.Series(price_proxy).diff().rolling(14).std().dropna().mean() or 0)
    vol_score = clamp((rolling_std / max(1.0, price_range)) * 1000, 0, 100)
    volatility = "Low" if vol_score < 18 else "Medium" if vol_score < 42 else "High"

    if normalized_slope > 0.16 and normalized_net > 0.10:
        trend = "Uptrend"
        bias = "Bullish"
    elif normalized_slope < -0.16 and normalized_net < -0.10:
        trend = "Downtrend"
        bias = "Bearish"
    else:
        trend = "Sideway"
        bias = "Neutral"

    confidence = int(clamp(45 + abs(normalized_slope) * 45 + abs(normalized_net) * 25 - (10 if trend == "Sideway" else 0), 35, 92))

    swing_highs, swing_lows = detect_swings(arr_y.tolist())
    resistance_y = np.percentile(arr_y, [10, 18, 25]).tolist()  # top visual areas
    support_y = np.percentile(arr_y, [75, 82, 90]).tolist()     # bottom visual areas

    current_y = arr_y[-1]
    near_resistance = current_y <= np.percentile(arr_y, 20)
    near_support = current_y >= np.percentile(arr_y, 80)
    recent = price_proxy[-max(10, len(price_proxy)//5):]
    previous_high = np.max(price_proxy[:-max(5, len(price_proxy)//10)]) if len(price_proxy) > 30 else np.max(price_proxy)
    previous_low = np.min(price_proxy[:-max(5, len(price_proxy)//10)]) if len(price_proxy) > 30 else np.min(price_proxy)

    if price_proxy[-1] > previous_high * 0.995 and normalized_slope > 0:
        breakout = "Potential breakout above visual resistance"
    elif price_proxy[-1] < previous_low * 1.005 and normalized_slope < 0:
        breakout = "Potential breakdown below visual support"
    elif near_resistance:
        breakout = "Price is testing visual resistance"
    elif near_support:
        breakout = "Price is testing visual support"
    else:
        breakout = "No clear breakout"

    liquidity_zones = []
    if swing_highs:
        liquidity_zones.append({"type": "Buy-side liquidity", "visual_y": round(float(np.mean([p["y"] for p in swing_highs[-3:]])), 2)})
    if swing_lows:
        liquidity_zones.append({"type": "Sell-side liquidity", "visual_y": round(float(np.mean([p["y"] for p in swing_lows[-3:]])), 2)})

    candle_read = (
        "Momentum is rising with higher visual closes." if trend == "Uptrend" else
        "Momentum is falling with lower visual closes." if trend == "Downtrend" else
        "Price movement appears compressed/ranging; wait for range break confirmation."
    )

    return {
        "trend": trend,
        "bias": bias,
        "confidence": confidence,
        "volatility": volatility,
        "volatility_score": round(vol_score, 2),
        "support_resistance": {
            "support_visual": [round(float(v), 2) for v in support_y],
            "resistance_visual": [round(float(v), 2) for v in resistance_y],
            "note": "Visual y-levels: lower y is higher price on the image.",
        },
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "breakout": breakout,
        "liquidity_zones": liquidity_zones,
        "candlestick_read": candle_read,
        "price_proxy": {
            "start": round(float(price_proxy[0]), 2),
            "end": round(float(price_proxy[-1]), 2),
            "range": round(float(price_range), 2),
            "normalized_slope": round(float(normalized_slope), 4),
            "normalized_net": round(float(normalized_net), 4),
        },
    }


def generate_trade_plan(analysis: Dict[str, Any], current_price: Optional[float] = None, data_mode: bool = False) -> Dict[str, Any]:
    trend = analysis.get("trend", "Sideway")
    bias = analysis.get("bias", "Neutral")
    confidence = safe_float(analysis.get("confidence"), 50) or 50
    volatility = analysis.get("volatility", "Medium")

    signal = "WAIT"
    if bias == "Bullish" and confidence >= 55:
        signal = "BUY"
    elif bias == "Bearish" and confidence >= 55:
        signal = "SELL"

    if current_price and current_price > 0:
        vol_pct = 0.006 if volatility == "Low" else 0.011 if volatility == "Medium" else 0.018
        if data_mode and analysis.get("atr"):
            atr = safe_float(analysis.get("atr"), current_price * vol_pct) or current_price * vol_pct
            risk = max(atr * 1.2, current_price * 0.002)
        else:
            risk = current_price * vol_pct

        if signal == "BUY":
            entry = current_price
            sl = entry - risk
            tp1 = entry + risk * 1.5
            tp2 = entry + risk * 2.5
        elif signal == "SELL":
            entry = current_price
            sl = entry + risk
            tp1 = entry - risk * 1.5
            tp2 = entry - risk * 2.5
        else:
            entry = current_price
            sl = None
            tp1 = None
            tp2 = None

        entry_plan = "Enter after confirmation candle closes in signal direction." if signal != "WAIT" else "Wait for breakout/retest or clearer structure."
        rr = "1:1.5 to 1:2.5" if signal != "WAIT" else "N/A"
    else:
        entry = sl = tp1 = tp2 = None
        entry_plan = "Use visual levels only. Confirm with live price before execution."
        rr = "N/A"

    risk_profiles = {
        "Conservative": "Use half position size; enter only after retest confirmation; risk <= 0.5% per trade.",
        "Balanced": "Use normal position size; enter on confirmation; risk around 1% per trade.",
        "Aggressive": "Allow earlier entry near signal zone; reduce size if volatility is high; risk max 1.5%.",
    }

    return {
        "signal": signal,
        "bias": bias,
        "entry_plan": entry_plan,
        "entry": round(entry, 5) if entry else None,
        "stop_loss": round(sl, 5) if sl else None,
        "take_profit_1": round(tp1, 5) if tp1 else None,
        "take_profit_2": round(tp2, 5) if tp2 else None,
        "risk_reward": rr,
        "risk_profile": risk_profiles,
        "execution_note": "Prototype signal only. Validate on TradingView/MT4/MT5 before placing orders.",
    }


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def analyze_ohlc_csv(file_bytes: bytes) -> Dict[str, Any]:
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read CSV: {exc}") from exc

    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = REQUIRED_CSV_COLUMNS - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV missing required columns: {', '.join(sorted(missing))}")

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    if len(df) < 60:
        raise HTTPException(status_code=400, detail="CSV needs at least 60 valid OHLC rows for EMA/RSI/ATR analysis.")

    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["rsi14"] = rsi(df["close"], 14)
    df["atr14"] = atr(df, 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(last["close"])
    ema20 = float(last["ema20"])
    ema50 = float(last["ema50"])
    rsi14 = float(last["rsi14"]) if not math.isnan(float(last["rsi14"])) else 50.0
    atr14 = float(last["atr14"]) if not math.isnan(float(last["atr14"])) else float((df["high"] - df["low"]).tail(14).mean())

    if ema20 > ema50 and close > ema20:
        trend = "Uptrend"
        bias = "Bullish"
    elif ema20 < ema50 and close < ema20:
        trend = "Downtrend"
        bias = "Bearish"
    else:
        trend = "Sideway"
        bias = "Neutral"

    ema_gap_pct = abs(ema20 - ema50) / close * 100
    atr_pct = atr14 / close * 100 if close else 0
    volatility = "Low" if atr_pct < 0.5 else "Medium" if atr_pct < 1.5 else "High"

    confidence = 50 + min(25, ema_gap_pct * 8)
    if (bias == "Bullish" and 45 <= rsi14 <= 72) or (bias == "Bearish" and 28 <= rsi14 <= 55):
        confidence += 15
    if volatility == "High":
        confidence -= 5
    confidence = int(clamp(confidence, 35, 94))

    breakout = "No clear breakout"
    recent_high = float(df["high"].tail(30).iloc[:-1].max())
    recent_low = float(df["low"].tail(30).iloc[:-1].min())
    if close > recent_high:
        breakout = "Breakout above recent 30-bar high"
    elif close < recent_low:
        breakout = "Breakdown below recent 30-bar low"

    analysis = {
        "trend": trend,
        "bias": bias,
        "confidence": confidence,
        "volatility": volatility,
        "current_price": close,
        "ema20": round(ema20, 5),
        "ema50": round(ema50, 5),
        "rsi14": round(rsi14, 2),
        "atr": round(atr14, 5),
        "atr_pct": round(atr_pct, 3),
        "breakout": breakout,
        "support_resistance": {
            "support": round(recent_low, 5),
            "resistance": round(recent_high, 5),
        },
        "rows_analyzed": int(len(df)),
        "last_time": str(last.get("time", "")),
    }
    plan = generate_trade_plan(analysis, current_price=close, data_mode=True)
    return build_unified_result(
        mode="csv",
        metadata={"symbol": "From CSV", "timeframe": "From CSV", "current_price": close},
        ocr={"available": False, "text": "", "error": "CSV mode does not use OCR"},
        image_analysis=None,
        data_analysis=analysis,
        trade_plan=plan,
    )


def ai_analysis_placeholder(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Future integration point for OpenAI/Gemini Vision.
    Send `payload` to a vision/language model, then merge model commentary here.
    """
    return {
        "ready": True,
        "provider": None,
        "message": "AI Vision integration placeholder. Unified JSON is ready to send to OpenAI/Gemini later.",
    }


def build_unified_result(
    mode: str,
    metadata: Dict[str, Any],
    ocr: Dict[str, Any],
    image_analysis: Optional[Dict[str, Any]],
    data_analysis: Optional[Dict[str, Any]],
    trade_plan: Dict[str, Any],
) -> Dict[str, Any]:
    core = data_analysis or image_analysis or {}
    payload = {
        "app": "Ray AI Trader",
        "mode": mode,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metadata": metadata,
        "ocr": ocr,
        "image_analysis": image_analysis,
        "data_analysis": data_analysis,
        "summary": {
            "symbol": metadata.get("symbol", "Unknown"),
            "timeframe": metadata.get("timeframe", "Unknown"),
            "trend": core.get("trend", "Unknown"),
            "signal": trade_plan.get("signal", "WAIT"),
            "bias": core.get("bias", "Neutral"),
            "confidence": core.get("confidence", 0),
            "volatility": core.get("volatility", "Unknown"),
        },
        "trade_plan": trade_plan,
        "risk_warning": "This is an educational prototype, not financial advice. Trading involves risk. Always confirm with live market data and your own risk management.",
    }
    payload["ai_analysis"] = ai_analysis_placeholder(payload)
    return payload


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze-image")
async def analyze_image(file: UploadFile = File(...)) -> JSONResponse:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use jpg, jpeg, png, or webp.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image upload.")

    image = read_image_upload(content)
    ocr = extract_ocr_text(image)
    metadata = detect_metadata(ocr.get("text", ""))
    analysis = image_chart_analysis(image, metadata)
    trade_plan = generate_trade_plan(analysis, current_price=metadata.get("current_price"), data_mode=False)
    result = build_unified_result("image", metadata, ocr, analysis, None, trade_plan)
    return JSONResponse(result)


@app.post("/analyze-csv")
async def analyze_csv(file: UploadFile = File(...)) -> JSONResponse:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty CSV upload.")
    return JSONResponse(analyze_ohlc_csv(content))


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_PAGE


HTML_PAGE = r'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Ray AI Trader</title>
  <style>
    :root{--bg:#070817;--panel:#101426;--panel2:#151a31;--line:#27304f;--text:#eef3ff;--muted:#96a3c7;--blue:#41a6ff;--purple:#9b5cff;--green:#35e39c;--red:#ff5c7a;--yellow:#ffd166;}
    *{box-sizing:border-box} body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top left,#16265d 0,#070817 38%,#050611 100%);color:var(--text);min-height:100vh}
    .wrap{max-width:1180px;margin:auto;padding:24px}.hero{display:grid;grid-template-columns:1.2fr .8fr;gap:18px;align-items:stretch}.card{background:linear-gradient(180deg,rgba(21,26,49,.94),rgba(10,13,27,.94));border:1px solid var(--line);border-radius:22px;box-shadow:0 20px 60px rgba(0,0,0,.35);padding:22px}.brand{display:flex;gap:12px;align-items:center}.logo{width:46px;height:46px;border-radius:15px;background:linear-gradient(135deg,var(--blue),var(--purple));display:grid;place-items:center;font-weight:900}.badge{display:inline-flex;gap:6px;align-items:center;padding:7px 10px;border-radius:999px;background:rgba(65,166,255,.12);border:1px solid rgba(65,166,255,.35);color:#bfe1ff;font-size:12px}.hero h1{font-size:42px;line-height:1.04;margin:18px 0 10px}.grad{background:linear-gradient(90deg,#65c7ff,#b488ff);-webkit-background-clip:text;color:transparent}.muted{color:var(--muted)}.tabs{display:flex;gap:10px;margin:18px 0}.tab{border:1px solid var(--line);background:#0b1024;color:var(--text);padding:11px 14px;border-radius:13px;cursor:pointer}.tab.active{border-color:var(--blue);background:rgba(65,166,255,.15)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}.drop{min-height:275px;border:1.5px dashed #4f5f95;border-radius:20px;padding:18px;display:grid;place-items:center;text-align:center;background:rgba(12,17,39,.72);transition:.2s}.drop.drag{border-color:var(--blue);background:rgba(65,166,255,.12)}input[type=file]{display:none}.btn{border:0;border-radius:14px;padding:13px 17px;color:white;background:linear-gradient(135deg,var(--blue),var(--purple));font-weight:800;cursor:pointer;box-shadow:0 12px 30px rgba(65,166,255,.25)}.btn.secondary{background:#161d38;border:1px solid var(--line);box-shadow:none}.btn.danger{background:rgba(255,92,122,.15);border:1px solid rgba(255,92,122,.5);color:#ffdbe2}.preview{max-width:100%;max-height:310px;border-radius:16px;border:1px solid var(--line);display:none}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.summary{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.metric{background:rgba(255,255,255,.04);border:1px solid var(--line);padding:15px;border-radius:16px}.metric b{display:block;font-size:22px;margin-top:6px}.signal-BUY{color:var(--green)}.signal-SELL{color:var(--red)}.signal-WAIT{color:var(--yellow)}.progress{height:10px;background:#202746;border-radius:999px;overflow:hidden}.bar{height:100%;background:linear-gradient(90deg,var(--blue),var(--purple));width:0%}pre{white-space:pre-wrap;word-break:break-word;background:#050814;border:1px solid var(--line);border-radius:16px;padding:15px;color:#d8e4ff;max-height:360px;overflow:auto}.hidden{display:none}.journal-item{display:flex;justify-content:space-between;gap:12px;border:1px solid var(--line);background:rgba(255,255,255,.035);border-radius:14px;padding:12px;margin:10px 0}.footer{margin-top:22px;text-align:center;color:var(--muted);font-size:13px}.warning{border-color:rgba(255,209,102,.35);background:rgba(255,209,102,.08)}
    @media(max-width:900px){.hero,.grid{grid-template-columns:1fr}.summary{grid-template-columns:1fr 1fr}.hero h1{font-size:34px}.wrap{padding:14px}} @media(max-width:560px){.summary{grid-template-columns:1fr}.row .btn{width:100%}}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="card">
        <div class="brand"><div class="logo">R</div><div><span class="badge">AI Analysis Ready</span><h1>Ray <span class="grad">AI Trader</span></h1></div></div>
        <p class="muted">Upload TradingView / MT4 / MT5 screenshots or OHLC CSV. The prototype detects trend, support/resistance, liquidity zones, indicators, signal, entry, SL and TP.</p>
        <div class="tabs"><button class="tab active" id="imageTab">Image Mode</button><button class="tab" id="csvTab">Data Mode CSV</button></div>
        <div id="imageMode">
          <div id="drop" class="drop">
            <div><h3>Drop chart image here</h3><p class="muted">or paste from clipboard / select JPG PNG WEBP</p><label class="btn" for="imageInput">Choose Image</label><input id="imageInput" type="file" accept=".jpg,.jpeg,.png,.webp,image/*" /></div>
            <img id="preview" class="preview" alt="preview" />
          </div>
          <div class="row" style="margin-top:14px"><button class="btn" id="analyzeImage">Analyze Chart</button><button class="btn secondary" id="clearImage">Clear</button></div>
        </div>
        <div id="csvMode" class="hidden">
          <div class="drop"><div><h3>Upload OHLC CSV</h3><p class="muted">Required: time, open, high, low, close. Optional: volume.</p><label class="btn" for="csvInput">Choose CSV</label><input id="csvInput" type="file" accept=".csv" /><p id="csvName" class="muted"></p></div></div>
          <div class="row" style="margin-top:14px"><button class="btn" id="analyzeCsv">Analyze CSV</button></div>
        </div>
      </div>
      <div class="card warning"><h3>Risk Warning</h3><p class="muted">This system is a prototype for education and research. It is not financial advice. Always confirm with live market data, position sizing, and your own risk rules.</p><div class="progress"><div id="confBar" class="bar"></div></div><p class="muted"><span id="status">Ready</span></p></div>
    </section>

    <section class="card" style="margin-top:18px">
      <h2>Dashboard</h2>
      <div class="summary">
        <div class="metric"><span class="muted">Symbol</span><b id="mSymbol">-</b></div>
        <div class="metric"><span class="muted">Timeframe</span><b id="mTf">-</b></div>
        <div class="metric"><span class="muted">Trend</span><b id="mTrend">-</b></div>
        <div class="metric"><span class="muted">Signal</span><b id="mSignal">-</b></div>
        <div class="metric"><span class="muted">Confidence</span><b id="mConf">0%</b></div>
      </div>
      <div class="grid">
        <div><h3>Trade Plan</h3><pre id="plan">No analysis yet.</pre></div>
        <div><h3>Technical Details</h3><pre id="details">No analysis yet.</pre></div>
      </div>
      <div class="row" style="margin-top:14px"><button class="btn secondary" id="exportReport">Export HTML Report</button><button class="btn secondary" id="saveJournal">Save to Journal</button></div>
    </section>

    <section class="card" style="margin-top:18px"><h2>Trade Journal</h2><div id="journal"></div></section>
    <div class="footer">Ray AI Trader · FastAPI + OpenCV + OCR + CSV Indicators · Render Ready</div>
  </main>
<script>
let imageFile=null,csvFile=null,lastResult=null;
const $=id=>document.getElementById(id);
function setStatus(t){$('status').textContent=t}
function showMode(mode){$('imageMode').classList.toggle('hidden',mode!=='image');$('csvMode').classList.toggle('hidden',mode!=='csv');$('imageTab').classList.toggle('active',mode==='image');$('csvTab').classList.toggle('active',mode==='csv')}
$('imageTab').onclick=()=>showMode('image'); $('csvTab').onclick=()=>showMode('csv');
function setImage(file){imageFile=file; const url=URL.createObjectURL(file); $('preview').src=url; $('preview').style.display='block'; $('drop').querySelector('div').style.display='none'}
$('imageInput').onchange=e=>{if(e.target.files[0])setImage(e.target.files[0])};
$('csvInput').onchange=e=>{csvFile=e.target.files[0]; $('csvName').textContent=csvFile?csvFile.name:''};
['dragenter','dragover'].forEach(ev=>$('drop').addEventListener(ev,e=>{e.preventDefault();$('drop').classList.add('drag')}));
['dragleave','drop'].forEach(ev=>$('drop').addEventListener(ev,e=>{e.preventDefault();$('drop').classList.remove('drag')}));
$('drop').addEventListener('drop',e=>{const f=e.dataTransfer.files[0]; if(f)setImage(f)});
document.addEventListener('paste',e=>{for(const item of e.clipboardData.items){if(item.type.startsWith('image/')){setImage(item.getAsFile());break}}});
$('clearImage').onclick=()=>{imageFile=null;$('preview').style.display='none';$('drop').querySelector('div').style.display='block'};
async function upload(url,file){const fd=new FormData();fd.append('file',file);const res=await fetch(url,{method:'POST',body:fd});const data=await res.json();if(!res.ok)throw new Error(data.detail||'Analysis failed');return data}
$('analyzeImage').onclick=async()=>{try{if(!imageFile)throw new Error('Please select or paste an image first.');setStatus('Analyzing image...');render(await upload('/analyze-image',imageFile));setStatus('Image analysis complete')}catch(e){setStatus(e.message)}};
$('analyzeCsv').onclick=async()=>{try{if(!csvFile)throw new Error('Please select CSV first.');setStatus('Analyzing CSV...');render(await upload('/analyze-csv',csvFile));setStatus('CSV analysis complete')}catch(e){setStatus(e.message)}};
function render(result){lastResult=result;const s=result.summary||{};$('mSymbol').textContent=s.symbol||'-';$('mTf').textContent=s.timeframe||'-';$('mTrend').textContent=s.trend||'-';$('mSignal').textContent=s.signal||'-';$('mSignal').className='signal-'+(s.signal||'WAIT');$('mConf').textContent=(s.confidence||0)+'%';$('confBar').style.width=(s.confidence||0)+'%';$('plan').textContent=JSON.stringify(result.trade_plan,null,2);$('details').textContent=JSON.stringify({metadata:result.metadata,ocr:result.ocr,image_analysis:result.image_analysis,data_analysis:result.data_analysis,ai_analysis:result.ai_analysis},null,2);}
function getJournal(){return JSON.parse(localStorage.getItem('rayTraderJournal')||'[]')} function setJournal(v){localStorage.setItem('rayTraderJournal',JSON.stringify(v));drawJournal()}
$('saveJournal').onclick=()=>{if(!lastResult)return setStatus('No result to save.');const j=getJournal();j.unshift(lastResult);setJournal(j.slice(0,30));setStatus('Saved to local journal')};
function drawJournal(){const j=getJournal();$('journal').innerHTML=j.length?'':'<p class="muted">No saved analysis.</p>';j.forEach((r,i)=>{const s=r.summary||{};const div=document.createElement('div');div.className='journal-item';div.innerHTML=`<div><b>${s.symbol||'-'} · ${s.signal||'-'} · ${s.trend||'-'}</b><p class="muted">${r.timestamp} · Confidence ${s.confidence||0}%</p></div><button class="btn danger" data-i="${i}">Delete</button>`;$('journal').appendChild(div)});document.querySelectorAll('[data-i]').forEach(b=>b.onclick=()=>{const j=getJournal();j.splice(+b.dataset.i,1);setJournal(j)})}
$('exportReport').onclick=()=>{if(!lastResult)return setStatus('No report to export.');const html=`<!doctype html><html><head><meta charset="utf-8"><title>Ray AI Trader Report</title><style>body{font-family:Arial;background:#080b18;color:#eef3ff;padding:30px}pre{background:#111832;padding:18px;border-radius:12px;white-space:pre-wrap}</style></head><body><h1>Ray AI Trader Report</h1><pre>${JSON.stringify(lastResult,null,2).replace(/[<>&]/g,m=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[m]))}</pre></body></html>`;const blob=new Blob([html],{type:'text/html'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ray-ai-trader-report.html';a.click()};
drawJournal();
</script>
</body></html>
'''

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
