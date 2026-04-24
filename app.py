from __future__ import annotations

import io
import math
import os
import re
from datetime import datetime
from typing import Any

import cv2
import numpy as np
import pytesseract
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image


APP_NAME = "Ray Investment Chart Analyzer"
APP_VERSION = "1.0.0"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Upload chart image and get basic technical analysis report.",
)


def preprocess_image(image_bytes: bytes) -> tuple[np.ndarray, Image.Image]:
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    np_img = np.array(pil_img)

    # Convert RGB -> BGR for OpenCV
    bgr = cv2.cvtColor(np_img, cv2.COLOR_RGB2BGR)
    return bgr, pil_img


def run_ocr(pil_img: Image.Image) -> str:
    """
    OCR is optional. If Tesseract is not available on the server,
    the app will continue to work with image-based analysis.
    """
    try:
        text = pytesseract.image_to_string(pil_img, lang="eng")
        return text.strip()
    except Exception as exc:
        return f"OCR unavailable: {exc}"


def extract_symbol_timeframe(ocr_text: str) -> dict[str, str | None]:
    text = ocr_text.replace("\n", " ")

    symbol = None
    timeframe = None

    symbol_patterns = [
        r"\bXAUUSD\b",
        r"\bBTCUSD\b",
        r"\bETHUSD\b",
        r"\b[A-Z]{1,6}USD\b",
        r"\b[A-Z]{1,5}\b",
    ]

    for pattern in symbol_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            symbol = match.group(0).upper()
            break

    tf_match = re.search(r"\b(1m|3m|5m|15m|30m|1h|4h|1d|M1|M3|M5|M15|M30|H1|H4|D1)\b", text)
    if tf_match:
        timeframe = tf_match.group(0).upper()

    return {"symbol": symbol, "timeframe": timeframe}


def detect_chart_trend(bgr: np.ndarray) -> dict[str, Any]:
    """
    Heuristic image-based trend detection.
    It does not replace real OHLC data analysis, but helps generate
    a first-pass read from a screenshot.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Crop center area to avoid browser/header/footer noise
    h, w = gray.shape
    crop = gray[int(h * 0.12): int(h * 0.90), int(w * 0.05): int(w * 0.95)]

    # Edge detection to capture candle/line activity
    edges = cv2.Canny(crop, 60, 160)

    # Find active pixels by vertical distribution
    ys, xs = np.where(edges > 0)

    if len(xs) < 200:
        return {
            "trend": "ไม่ชัดเจน",
            "confidence": 35,
            "slope": 0,
            "note": "ภาพมีข้อมูลกราฟไม่เพียงพอ หรือเส้นกราฟ/แท่งเทียนไม่ชัด",
        }

    # Split into vertical slices and find median price-position per slice.
    # In image coordinates, lower y means higher price.
    slices = 24
    med_points = []
    for i in range(slices):
        x1 = int(i * crop.shape[1] / slices)
        x2 = int((i + 1) * crop.shape[1] / slices)
        mask = (xs >= x1) & (xs < x2)
        if np.sum(mask) > 10:
            med_y = float(np.median(ys[mask]))
            med_points.append((i, med_y))

    if len(med_points) < 6:
        return {
            "trend": "ไม่ชัดเจน",
            "confidence": 40,
            "slope": 0,
            "note": "ตรวจจับจุดราคาในกราฟได้น้อยเกินไป",
        }

    x_arr = np.array([p[0] for p in med_points], dtype=float)
    y_arr = np.array([p[1] for p in med_points], dtype=float)

    # Linear regression slope. Negative y slope = price visually moving up.
    slope = float(np.polyfit(x_arr, y_arr, 1)[0])
    y_std = float(np.std(y_arr))
    normalized = abs(slope) / max(y_std, 1.0)

    if slope < -1.2:
        trend = "ขาขึ้น"
    elif slope > 1.2:
        trend = "ขาลง"
    else:
        trend = "Sideway / แกว่งตัว"

    confidence = int(min(85, max(45, 45 + normalized * 90)))

    return {
        "trend": trend,
        "confidence": confidence,
        "slope": round(slope, 4),
        "note": "เป็นการประเมินจากภาพ Screenshot เบื้องต้น ควรยืนยันด้วยราคา OHLC จริง",
    }


def estimate_support_resistance(bgr: np.ndarray) -> dict[str, Any]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    crop = gray[int(h * 0.12): int(h * 0.90), int(w * 0.05): int(w * 0.95)]

    edges = cv2.Canny(crop, 60, 160)
    row_strength = edges.sum(axis=1)

    if row_strength.max() <= 0:
        return {"support_zone": None, "resistance_zone": None, "note": "ตรวจจับแนวรับแนวต้านไม่ได้"}

    # Rows with high edge density may represent repeated price activity / horizontal levels
    threshold = np.percentile(row_strength, 92)
    strong_rows = np.where(row_strength >= threshold)[0]

    if len(strong_rows) == 0:
        return {"support_zone": None, "resistance_zone": None, "note": "ยังไม่พบโซนราคาเด่น"}

    top_zone = int(np.percentile(strong_rows, 20))
    bottom_zone = int(np.percentile(strong_rows, 80))

    return {
        "resistance_zone_visual_y": top_zone,
        "support_zone_visual_y": bottom_zone,
        "note": "ค่า y เป็นตำแหน่งเชิงภาพ ไม่ใช่ราคาจริง ถ้าต้องการราคาจริงควรส่งข้อมูล OHLC หรือ OCR ที่อ่านราคาได้ชัดเจน",
    }


def build_trade_bias(trend: str, confidence: int) -> dict[str, str]:
    if confidence < 55 or trend == "ไม่ชัดเจน":
        return {
            "bias": "รอดูจังหวะ",
            "entry_plan": "ยังไม่ควรรีบเข้า รอราคาเบรกกรอบหรือเกิดสัญญาณกลับตัวชัดเจน",
            "risk": "สูง หากเข้าโดยไม่มี confirmation",
        }

    if trend == "ขาขึ้น":
        return {
            "bias": "เน้น Buy ตามเทรนด์",
            "entry_plan": "รอ Pullback เข้าใกล้แนวรับ / EMA / Demand zone แล้วค่อยหาจังหวะเข้า",
            "risk": "วาง SL ใต้ swing low ล่าสุด และลด lot หากราคาเริ่มหลุดโครงสร้าง",
        }

    if trend == "ขาลง":
        return {
            "bias": "เน้น Sell ตามเทรนด์",
            "entry_plan": "รอ Pullback เข้าใกล้แนวต้าน / Supply zone แล้วค่อยหาจังหวะเข้า",
            "risk": "วาง SL เหนือ swing high ล่าสุด และระวังแรงเด้งจากโซน demand",
        }

    return {
        "bias": "เล่นในกรอบ Sideway",
        "entry_plan": "เน้นซื้อใกล้แนวรับ ขายใกล้แนวต้าน หรือรอ Breakout แล้วตาม",
        "risk": "ระวัง False Break และควรลดขนาดการเข้าไม้",
    }


def analyze_chart(image_bytes: bytes) -> dict[str, Any]:
    bgr, pil_img = preprocess_image(image_bytes)
    ocr_text = run_ocr(pil_img)
    meta = extract_symbol_timeframe(ocr_text)
    trend_data = detect_chart_trend(bgr)
    levels = estimate_support_resistance(bgr)
    trade = build_trade_bias(trend_data["trend"], trend_data["confidence"])

    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "metadata": meta,
        "trend_analysis": trend_data,
        "support_resistance": levels,
        "trade_plan": trade,
        "ocr_text_preview": ocr_text[:1200],
        "disclaimer": "ผลวิเคราะห์นี้เป็นข้อมูลเชิงเทคนิคเบื้องต้นจากภาพ ไม่ใช่คำแนะนำการลงทุน ควรใช้ร่วมกับข้อมูลราคาและการบริหารความเสี่ยง",
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ray Investment Chart Analyzer</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #111827;
      --card2: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --good: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, "Noto Sans Thai", sans-serif;
      background: radial-gradient(circle at top, #1e3a8a 0, var(--bg) 42%);
      color: var(--text);
      min-height: 100vh;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 32px 18px; }
    .hero {
      display: grid;
      gap: 16px;
      margin-bottom: 22px;
    }
    h1 { font-size: clamp(28px, 4vw, 48px); margin: 0; letter-spacing: -0.04em; }
    p { color: var(--muted); line-height: 1.7; }
    .card {
      background: rgba(17, 24, 39, .86);
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 22px;
      padding: 22px;
      box-shadow: 0 24px 80px rgba(0,0,0,.28);
    }
    .upload {
      display: grid;
      gap: 14px;
    }
    input[type=file] {
      width: 100%;
      padding: 18px;
      border: 1px dashed rgba(255,255,255,.28);
      border-radius: 16px;
      background: var(--card2);
      color: var(--text);
    }
    button {
      border: 0;
      border-radius: 14px;
      padding: 14px 18px;
      background: linear-gradient(135deg, #38bdf8, #2563eb);
      color: white;
      font-size: 16px;
      cursor: pointer;
      font-weight: 700;
    }
    button:disabled { opacity: .55; cursor: wait; }
    .result {
      margin-top: 22px;
      display: grid;
      gap: 14px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 14px;
    }
    .mini {
      background: rgba(31, 41, 55, .8);
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 16px;
      padding: 16px;
    }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
    .value { font-size: 22px; font-weight: 800; }
    pre {
      white-space: pre-wrap;
      overflow: auto;
      background: #020617;
      color: #cbd5e1;
      border-radius: 16px;
      padding: 16px;
      line-height: 1.55;
    }
    @media (max-width: 760px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Ray Investment Chart Analyzer</h1>
      <p>อัปโหลดภาพกราฟจาก TradingView / MT5 / Screenshot แล้วระบบจะวิเคราะห์แนวโน้ม แนวรับแนวต้านเชิงภาพ และ Bias การเทรดเบื้องต้น</p>
    </section>

    <section class="card">
      <form class="upload" id="form">
        <input id="file" name="file" type="file" accept="image/png,image/jpeg,image/webp" required>
        <button id="btn" type="submit">Analyze Chart</button>
      </form>

      <div id="result" class="result"></div>
    </section>
  </main>

<script>
const form = document.getElementById("form");
const btn = document.getElementById("btn");
const result = document.getElementById("result");

function esc(v) {
  return String(v ?? "-").replace(/[&<>"']/g, s => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[s]));
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = document.getElementById("file").files[0];
  if (!file) return;

  btn.disabled = true;
  btn.textContent = "Analyzing...";
  result.innerHTML = "<p>กำลังวิเคราะห์ภาพกราฟ...</p>";

  const data = new FormData();
  data.append("file", file);

  try {
    const res = await fetch("/analyze", { method: "POST", body: data });
    const json = await res.json();

    if (!res.ok) throw new Error(json.detail || "Analyze failed");

    const trend = json.trend_analysis || {};
    const trade = json.trade_plan || {};
    const meta = json.metadata || {};

    result.innerHTML = `
      <div class="grid">
        <div class="mini">
          <div class="label">Symbol</div>
          <div class="value">${esc(meta.symbol || "Unknown")}</div>
        </div>
        <div class="mini">
          <div class="label">Timeframe</div>
          <div class="value">${esc(meta.timeframe || "Unknown")}</div>
        </div>
        <div class="mini">
          <div class="label">Trend</div>
          <div class="value">${esc(trend.trend)} (${esc(trend.confidence)}%)</div>
        </div>
      </div>

      <div class="mini">
        <div class="label">Trade Bias</div>
        <div class="value">${esc(trade.bias)}</div>
        <p>${esc(trade.entry_plan)}</p>
        <p><strong>Risk:</strong> ${esc(trade.risk)}</p>
      </div>

      <pre>${esc(JSON.stringify(json, null, 2))}</pre>
    `;
  } catch (err) {
    result.innerHTML = `<p style="color:#fca5a5">Error: ${esc(err.message)}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze Chart";
  }
});
</script>
</body>
</html>
"""


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)) -> JSONResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        return JSONResponse(status_code=400, content={"detail": "Please upload an image file."})

    image_bytes = await file.read()

    if len(image_bytes) > 8 * 1024 * 1024:
        return JSONResponse(status_code=400, content={"detail": "Image file is too large. Max 8MB."})

    try:
        report = analyze_chart(image_bytes)
        return JSONResponse(content=report)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"Analyze error: {exc}"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
