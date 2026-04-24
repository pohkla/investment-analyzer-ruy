# Ray AI Trader

Ray AI Trader is a FastAPI web app for prototype trading-chart analysis from screenshots and OHLC CSV data.

## Features

- Upload chart images from TradingView / MT4 / MT5 / mobile screenshots
- Drag & drop image upload
- Paste image from clipboard
- Preview before analysis
- OCR text extraction with safe fallback if OCR is unavailable
- Metadata detection: symbol, timeframe, detected prices
- OpenCV heuristic chart analysis:
  - trend detection
  - confidence score
  - volatility estimate
  - swing high / swing low
  - visual support / resistance
  - breakout / breakdown estimate
  - liquidity zone estimate
- CSV Data Mode with indicators:
  - EMA 20
  - EMA 50
  - RSI 14
  - ATR 14
- Trade plan generator:
  - BUY / SELL / WAIT
  - Entry
  - Stop Loss
  - Take Profit 1 / 2
  - Risk/Reward
  - Conservative / Balanced / Aggressive risk profile
- Dashboard result view
- Export HTML report
- Local Trade Journal using browser localStorage
- AI-ready unified JSON with `ai_analysis_placeholder()`

## Files

```text
app.py
requirements.txt
render.yaml
README.md
```

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## CSV Format

Required columns:

```csv
time,open,high,low,close,volume
2026-01-01 09:00,100,105,98,103,1200
```

At least 60 valid OHLC rows are required.

## Deploy on Render

1. Create a GitHub repository.
2. Upload these files to the repository root:
   - `app.py`
   - `requirements.txt`
   - `render.yaml`
   - `README.md`
3. Go to Render Dashboard.
4. Choose **New +** → **Blueprint**.
5. Connect the GitHub repository.
6. Render will read `render.yaml` automatically.
7. Deploy.

The app uses:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: uvicorn app:app --host 0.0.0.0 --port $PORT
```

## OCR Note

`pytesseract` is included as a Python package. Some Render environments may not include the system `tesseract` binary by default. If OCR is unavailable, the app will not crash; it returns `OCR unavailable` and continues image-based analysis.

For production OCR on Render, add a Dockerfile or install system package `tesseract-ocr` in the build environment.

## Disclaimer

This app is a prototype for education and research. It is not financial advice. Always confirm with live market data and proper risk management before trading.
