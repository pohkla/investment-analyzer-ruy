# Ray AI Trader 🚀
Visual & Data-driven Market Analysis Tool.

## Features
- **Visual Analysis**: Detects trends and support/resistance using OpenCV.
- **OCR Integration**: Extracts symbols and timeframes from screenshots.
- **Data Mode**: Analyzes OHLC CSV files with technical indicators (EMA, RSI).
- **Modern UI**: Dark mode dashboard with drag-and-drop & clipboard support.

## Setup & Local Run
1. Install Tesseract OCR on your machine.
2. `pip install -r requirements.txt`
3. `python app.py`

## Deploy to Render
1. Create a new Web Service on Render.
2. Connect your GitHub Repo.
3. Render will automatically detect `render.yaml`.
4. Ensure the environment is set to Python.