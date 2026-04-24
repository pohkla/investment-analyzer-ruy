import os
import io
import cv2
import numpy as np
import pandas as pd
import pytesseract
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import base64

app = FastAPI(title="Ray AI Trader API")

# Configuration for Tesseract (If running locally, specify path if needed)
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

# --- Logic: Image Analysis (Heuristic OpenCV) ---
def analyze_chart_image(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # OCR Attempt
    ocr_text = ""
    try:
        ocr_text = pytesseract.image_to_string(gray)
    except Exception:
        ocr_text = "OCR unavailable"

    # Simple Trend Analysis via Edge Detection & Slopes
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)
    
    ups, downs = 0, 0
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            slope = (y2 - y1) / (x2 - x1) if (x2 - x1) != 0 else 0
            if slope < -0.1: ups += 1  # In image coords, negative slope is upward
            elif slope > 0.1: downs += 1

    trend = "Sideway"
    confidence = 50
    if ups > downs * 1.5:
        trend = "Uptrend"
        confidence = min(85, 50 + (ups - downs))
    elif downs > ups * 1.5:
        trend = "Downtrend"
        confidence = min(85, 50 + (downs - ups))

    # Mock Price Extraction (Heuristic)
    symbol = "Unknown"
    for s in ["XAUUSD", "BTC", "ETH", "NAS100", "US30", "GBPUSD"]:
        if s in ocr_text.upper():
            symbol = s
            break

    return {
        "symbol": symbol,
        "trend": trend,
        "confidence": confidence,
        "ocr_raw": ocr_text[:200],
        "signal": "BUY" if trend == "Uptrend" else "SELL" if trend == "Downtrend" else "WAIT"
    }

# --- Logic: CSV Data Analysis ---
def analyze_csv_data(df):
    try:
        df.columns = [c.lower() for c in df.columns]
        # Indicators
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        signal = "WAIT"
        bias = "Neutral"
        
        if last['ema20'] > last['ema50'] and last['rsi'] < 70:
            signal = "BUY"
            bias = "Bullish"
        elif last['ema20'] < last['ema50'] and last['rsi'] > 30:
            signal = "SELL"
            bias = "Bearish"
            
        return {
            "symbol": "Data Upload",
            "trend": bias,
            "signal": signal,
            "current_price": round(last['close'], 2),
            "rsi": round(last['rsi'], 2),
            "ema20": round(last['ema20'], 2),
            "tp": round(last['close'] * 1.02, 2) if signal == "BUY" else round(last['close'] * 0.98, 2),
            "sl": round(last['close'] * 0.99, 2) if signal == "BUY" else round(last['close'] * 1.01, 2)
        }
    except Exception as e:
        return {"error": str(e)}

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ray AI Trader</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            body { background-color: #0b0e14; color: #e5e7eb; font-family: 'Inter', sans-serif; }
            .glass { background: rgba(23, 27, 34, 0.8); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1); }
            .accent-blue { color: #3b82f6; }
            .bg-gradient { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
            .drop-zone { border: 2px dashed #3b82f6; transition: all 0.3s ease; }
            .drop-zone.dragover { background: rgba(59, 130, 246, 0.1); border-color: #60a5fa; }
        </style>
    </head>
    <body class="p-4 md:p-8">
        <div class="max-w-6xl mx-auto">
            <header class="flex justify-between items-center mb-8">
                <div>
                    <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500">RAY AI TRADER</h1>
                    <p class="text-gray-400 text-sm">Next-Gen Visual Chart Analysis</p>
                </div>
                <div class="flex gap-4">
                    <button onclick="toggleMode('image')" id="btn-img" class="px-4 py-2 rounded bg-blue-600 text-white">Image Mode</button>
                    <button onclick="toggleMode('csv')" id="btn-csv" class="px-4 py-2 rounded bg-gray-700">Data Mode (CSV)</button>
                </div>
            </header>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div class="lg:col-span-1 space-y-6">
                    <div id="image-upload-section" class="glass p-6 rounded-xl">
                        <h2 class="text-xl font-semibold mb-4"><i class="fas fa-image mr-2"></i> Upload Chart</h2>
                        <div id="drop-zone" class="drop-zone p-8 rounded-lg text-center cursor-pointer">
                            <i class="fas fa-cloud-upload-alt text-4xl mb-3 text-blue-500"></i>
                            <p class="text-sm text-gray-400">Drag & Drop or Paste Image</p>
                            <input type="file" id="file-input" class="hidden" accept="image/*">
                        </div>
                        <div id="preview-container" class="mt-4 hidden">
                            <img id="img-preview" class="w-full rounded border border-gray-700 shadow-lg">
                            <button onclick="analyzeImage()" class="w-full mt-4 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg font-bold transition">ANALYZE CHART</button>
                        </div>
                    </div>

                    <div id="csv-upload-section" class="glass p-6 rounded-xl hidden">
                        <h2 class="text-xl font-semibold mb-4"><i class="fas fa-file-csv mr-2"></i> Upload CSV</h2>
                        <input type="file" id="csv-input" class="w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-600 file:text-white hover:file:bg-blue-700" accept=".csv">
                        <button onclick="analyzeCSV()" class="w-full mt-4 bg-purple-600 hover:bg-purple-700 text-white py-2 rounded-lg font-bold transition">PROCESS DATA</button>
                    </div>
                </div>

                <div class="lg:col-span-2 space-y-6">
                    <div id="result-placeholder" class="glass p-12 rounded-xl text-center flex flex-col items-center justify-center">
                        <i class="fas fa-robot text-6xl text-gray-700 mb-4"></i>
                        <p class="text-gray-500">Waiting for data to analyze...</p>
                    </div>

                    <div id="result-display" class="hidden space-y-6">
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div class="glass p-4 rounded-lg">
                                <p class="text-xs text-gray-400">SYMBOL</p>
                                <p id="res-symbol" class="text-xl font-bold text-blue-400">-</p>
                            </div>
                            <div class="glass p-4 rounded-lg">
                                <p class="text-xs text-gray-400">SIGNAL</p>
                                <p id="res-signal" class="text-xl font-bold">-</p>
                            </div>
                            <div class="glass p-4 rounded-lg">
                                <p class="text-xs text-gray-400">TREND</p>
                                <p id="res-trend" class="text-xl font-bold">-</p>
                            </div>
                            <div class="glass p-4 rounded-lg">
                                <p class="text-xs text-gray-400">CONFIDENCE</p>
                                <p id="res-conf" class="text-xl font-bold text-green-400">-</p>
                            </div>
                        </div>

                        <div class="glass p-6 rounded-xl border-l-4 border-blue-500">
                            <h3 class="text-lg font-bold mb-4 flex items-center">
                                <i class="fas fa-clipboard-list mr-2"></i> PROPOSED TRADE PLAN
                            </h3>
                            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div>
                                    <p class="text-sm text-gray-400">Entry Zone</p>
                                    <p id="plan-entry" class="text-lg font-mono font-bold text-white">Calculating...</p>
                                </div>
                                <div>
                                    <p class="text-sm text-gray-400 text-red-400">Stop Loss</p>
                                    <p id="plan-sl" class="text-lg font-mono font-bold text-red-400">Calculating...</p>
                                </div>
                                <div>
                                    <p class="text-sm text-gray-400 text-green-400">Take Profit (Main)</p>
                                    <p id="plan-tp" class="text-lg font-mono font-bold text-green-400">Calculating...</p>
                                </div>
                            </div>
                        </div>

                        <div class="glass p-6 rounded-xl">
                            <div class="flex justify-between items-center mb-4">
                                <h3 class="font-bold">Recent History</h3>
                                <button onclick="clearHistory()" class="text-xs text-gray-500 hover:text-red-400">Clear All</button>
                            </div>
                            <div id="history-list" class="space-y-2 text-sm">
                                </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let currentMode = 'image';
            const dropZone = document.getElementById('drop-zone');
            const fileInput = document.getElementById('file-input');
            const imgPreview = document.getElementById('img-preview');

            // Handle Drag & Drop
            dropZone.onclick = () => fileInput.click();
            dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('dragover'); };
            dropZone.ondragleave = () => dropZone.classList.remove('dragover');
            dropZone.ondrop = (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
                handleFile(e.dataTransfer.files[0]);
            };

            // Handle Paste
            window.onpaste = (e) => {
                const items = e.clipboardData.items;
                for (let item of items) {
                    if (item.type.indexOf("image") !== -1) {
                        handleFile(item.getAsFile());
                    }
                }
            };

            fileInput.onchange = (e) => handleFile(e.target.files[0]);

            function handleFile(file) {
                if (!file) return;
                const reader = new FileReader();
                reader.onload = (e) => {
                    imgPreview.src = e.target.result;
                    document.getElementById('preview-container').classList.remove('hidden');
                };
                reader.readAsDataURL(file);
            }

            function toggleMode(mode) {
                currentMode = mode;
                document.getElementById('image-upload-section').classList.toggle('hidden', mode !== 'image');
                document.getElementById('csv-upload-section').classList.toggle('hidden', mode !== 'csv');
                document.getElementById('btn-img').className = mode === 'image' ? 'px-4 py-2 rounded bg-blue-600 text-white' : 'px-4 py-2 rounded bg-gray-700';
                document.getElementById('btn-csv').className = mode === 'csv' ? 'px-4 py-2 rounded bg-purple-600 text-white' : 'px-4 py-2 rounded bg-gray-700';
            }

            async function analyzeImage() {
                const file = fileInput.files[0] || await fetch(imgPreview.src).then(r => r.blob());
                const formData = new FormData();
                formData.append('file', file);

                showLoading();
                try {
                    const res = await fetch('/analyze-image', { method: 'POST', body: formData });
                    const data = await res.json();
                    displayResult(data);
                    saveToJournal(data);
                } catch (err) { alert("Analysis failed"); }
            }

            async function analyzeCSV() {
                const file = document.getElementById('csv-input').files[0];
                if(!file) return alert("Select CSV first");
                const formData = new FormData();
                formData.append('file', file);

                showLoading();
                try {
                    const res = await fetch('/analyze-csv', { method: 'POST', body: formData });
                    const data = await res.json();
                    displayResult(data);
                } catch (err) { alert("CSV Analysis failed. Ensure columns: time, open, high, low, close"); }
            }

            function displayResult(data) {
                document.getElementById('result-placeholder').classList.add('hidden');
                document.getElementById('result-display').classList.remove('hidden');
                
                document.getElementById('res-symbol').innerText = data.symbol || 'N/A';
                document.getElementById('res-signal').innerText = data.signal;
                document.getElementById('res-signal').className = `text-xl font-bold ${data.signal === 'BUY' ? 'text-green-400' : data.signal === 'SELL' ? 'text-red-400' : 'text-gray-400'}`;
                document.getElementById('res-trend').innerText = data.trend;
                document.getElementById('res-conf').innerText = (data.confidence || 70) + '%';
                
                document.getElementById('plan-entry').innerText = data.current_price || "Market Price";
                document.getElementById('plan-sl').innerText = data.sl || "Auto SL (Visual)";
                document.getElementById('plan-tp').innerText = data.tp || "Auto TP (Visual)";
            }

            function showLoading() {
                document.getElementById('result-placeholder').innerHTML = '<i class="fas fa-spinner fa-spin text-4xl text-blue-500"></i><p class="mt-4">Analyzing Market Structure...</p>';
            }

            function saveToJournal(data) {
                let history = JSON.parse(localStorage.getItem('ray_journal') || '[]');
                history.unshift({ ...data, date: new Date().toLocaleString() });
                localStorage.setItem('ray_journal', JSON.stringify(history.slice(0, 10)));
                loadHistory();
            }

            function loadHistory() {
                const history = JSON.parse(localStorage.getItem('ray_journal') || '[]');
                const container = document.getElementById('history-list');
                container.innerHTML = history.map(h => `
                    <div class="flex justify-between p-2 bg-white/5 rounded">
                        <span>${h.date} - <b>${h.symbol}</b></span>
                        <span class="${h.signal === 'BUY' ? 'text-green-400' : 'text-red-400'}">${h.signal}</span>
                    </div>
                `).join('');
            }
            
            function clearHistory() { localStorage.removeItem('ray_journal'); loadHistory(); }
            window.onload = loadHistory;
        </script>
    </body>
    </html>
    """

@app.post("/analyze-image")
async def api_analyze_image(file: UploadFile = File(...)):
    contents = await file.read()
    result = analyze_chart_image(contents)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid image")
    return JSONResponse(content=result)

@app.post("/analyze-csv")
async def api_analyze_csv(file: UploadFile = File(...)):
    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
    result = analyze_csv_data(df)
    return JSONResponse(content=result)

@app.get("/health")
async def health():
    return {"status": "ok", "engine": "RayAI-v1"}

# For Future Expansion
def ai_analysis_placeholder(ocr_data, cv_data, csv_data):
    # This structure is ready for OpenAI Vision or Gemini Pro Vision
    payload = {
        "context": "Professional Trader Analysis",
        "visual_data": cv_data,
        "text_data": ocr_data,
        "numeric_data": csv_data
    }
    return payload

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)