# Ray Gold Guardian Bot

เว็บบอทช่วยเทรดทอง XAUUSD แบบ Real-time Webhook Ready สำหรับ Deploy บน Render

## ความสามารถใน v1.1

- FastAPI Backend
- WebSocket `/ws/xauusd` สำหรับ Real-time update
- TradingView Webhook Receiver `/api/tradingview/webhook`
- API ดึงแท่งย้อนหลัง `/api/xauusd/history`
- API วิเคราะห์สถานะตลาด `/api/xauusd/analysis`
- Dashboard กราฟ Candlestick ด้วย Lightweight Charts
- Risk Manager และ Lot Calculator
- Signal Panel: Market Mode, Action, Entry, SL, TP, Confidence
- Simulated feed fallback สำหรับทดสอบก่อนต่อข้อมูลจริง

> หมายเหตุ: TradingView Webhook ใช้ส่ง Alert เข้าเว็บเรา แต่ TradingView ไม่ได้เป็น API สำหรับดึงราคาสดแบบเปิดทั่วไปโดยตรงในโปรเจกต์นี้ ดังนั้นระบบนี้ออกแบบให้รับราคา/สัญญาณจาก TradingView Alert หรือเชื่อม Broker/MT5/Data Feed เพิ่มภายหลัง

## วิธีรันบนเครื่อง

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

เปิดเว็บ:

```text
http://127.0.0.1:8000
```

## วิธี Deploy ขึ้น GitHub + Render

1. แตกไฟล์ ZIP นี้
2. สร้าง GitHub Repository ใหม่ เช่น `ray-gold-guardian-bot`
3. Upload ไฟล์ทั้งหมดขึ้น GitHub
4. เข้า Render > New > Web Service
5. Connect GitHub Repository
6. Render จะอ่าน `render.yaml` ให้อัตโนมัติ
7. ตั้ง Environment Variables:

```text
TRADINGVIEW_WEBHOOK_SECRET=ตั้งรหัสลับของคุณเอง
ENABLE_SIMULATED_FEED=true
INITIAL_XAUUSD_PRICE=3343.10
SYMBOL=XAUUSD
```

8. กด Deploy

## TradingView Alert Webhook

หลัง Deploy แล้ว URL จะเป็นประมาณนี้:

```text
https://YOUR-APP.onrender.com/api/tradingview/webhook
```

ใส่ในช่อง Webhook URL ของ TradingView Alert

ตัวอย่าง Message:

```json
{
  "symbol": "{{ticker}}",
  "price": "{{close}}",
  "time": "{{time}}",
  "interval": "{{interval}}",
  "signal": "XAUUSD_ALERT",
  "message": "Price reached key zone",
  "secret": "ใส่ค่าเดียวกับ TRADINGVIEW_WEBHOOK_SECRET"
}
```

## Endpoint สำคัญ

```text
GET  /api/health
GET  /api/xauusd/history?tf=M1&limit=300
GET  /api/xauusd/analysis?balance=300&risk_percent=1&sl_points=55
POST /api/tradingview/webhook
WS   /ws/xauusd
```

## การต่อข้อมูลจริงในขั้นต่อไป

ถ้าต้องการราคา Real-time แบบ Tick จริง ให้เพิ่ม connector แหล่งข้อมูล เช่น:

- MT5 Python bridge บน VPS/เครื่องที่เปิด MT5
- Broker API ที่มี XAUUSD feed
- Data provider ที่มี precious metals real-time feed
- TradingView Alert หลายชุดเพื่อส่ง OHLC/Signal ตามเงื่อนไขที่ตั้งไว้

แนะนำสำหรับระบบเทรดจริง:

```text
TradingView Alert / Broker Feed / MT5
        ↓
FastAPI Backend
        ↓
Analysis Engine + Risk Guard
        ↓
WebSocket Dashboard
        ↓
Telegram/LINE Alert
        ↓
Manual หรือ Auto Execution
```

## คำเตือน

ระบบนี้เป็นเครื่องมือช่วยวิเคราะห์และจัดการความเสี่ยง ไม่ใช่คำแนะนำการลงทุนหรือการันตีกำไร ควร Backtest และ Forward Test ก่อนใช้งานจริงทุกครั้ง

---

## v1.2 Live Price Feed จริง

เวอร์ชันนี้เพิ่ม Live Price Connector สำหรับดึงราคาจริงเข้าระบบแบบ polling แล้วส่งต่อเข้า Dashboard ผ่าน WebSocket

### วิธีที่แนะนำ: Twelve Data

สมัคร API Key ที่ Twelve Data แล้วตั้ง Environment Variables ใน Render:

```env
PYTHON_VERSION=3.11.9
LIVE_PRICE_PROVIDER=twelvedata
TWELVEDATA_API_KEY=YOUR_TWELVEDATA_API_KEY
TWELVEDATA_SYMBOL=XAU/USD
LIVE_POLL_SECONDS=5
ENABLE_SIMULATED_FEED=false
SYMBOL=XAUUSD
INITIAL_XAUUSD_PRICE=4540.00
TRADINGVIEW_WEBHOOK_SECRET=YOUR_SECRET
```

### อีกทางเลือก: GoldAPI

```env
PYTHON_VERSION=3.11.9
LIVE_PRICE_PROVIDER=goldapi
GOLDAPI_KEY=YOUR_GOLDAPI_KEY
GOLDAPI_SYMBOL=XAU
GOLDAPI_CURRENCY=USD
LIVE_POLL_SECONDS=5
ENABLE_SIMULATED_FEED=false
SYMBOL=XAUUSD
INITIAL_XAUUSD_PRICE=4540.00
TRADINGVIEW_WEBHOOK_SECRET=YOUR_SECRET
```

### ทดสอบหลัง Deploy

```text
/api/health
/api/xauusd/live-price
/api/xauusd/analysis
```

ถ้า `/api/xauusd/live-price` ส่งกลับ `ok: true` และมี `price` แปลว่า Live Feed เชื่อมสำเร็จ

### หมายเหตุสำคัญ

TradingView Webhook ไม่ใช่ tick stream ต่อเนื่อง โดยจะส่งข้อมูลเข้าระบบเฉพาะเมื่อ Alert ถูก trigger เท่านั้น ถ้าต้องการราคาจริงแบบต่อเนื่อง ให้ใช้ `LIVE_PRICE_PROVIDER=twelvedata` หรือ `goldapi` หรือเชื่อม MT5/Broker API โดยตรง

## v1.3 Image Upload Analysis Ready

เวอร์ชันนี้เปลี่ยนพื้นที่กราฟหลักให้เป็นช่องอัปโหลดรูปภาพกราฟ เพื่อให้ผู้ใช้งานส่งภาพจาก TradingView / MT5 / MT4 เข้ามาประกอบการวิเคราะห์ได้โดยตรง

### API เพิ่มใหม่

```http
POST /api/chart-image/upload
```

Form data:

- `file`: รูปภาพกราฟ รองรับ PNG, JPG/JPEG, WEBP
- `note`: ข้อความประกอบ เช่น Timeframe หรือสิ่งที่ต้องการให้วิเคราะห์

ระบบจะบันทึกภาพไว้ที่ `/static/uploads/...` และส่งผลกลับเป็น `image_url`, metadata และ `analysis_hint`

### Dependency เพิ่มใหม่

```txt
python-multipart==0.0.20
```

ใช้สำหรับรับ multipart file upload ผ่าน FastAPI

### หมายเหตุ

- การอัปโหลดภาพตอนนี้เป็น Image Context Mode สำหรับเก็บภาพและใช้ประกอบการวิเคราะห์ร่วมกับราคา Real-time
- หากต้องการให้ระบบอ่านภาพกราฟแบบ Vision AI จริง เช่น อ่านแท่งเทียน เส้น EMA, RSI, S/R จากรูปภาพโดยตรง ให้ต่อ OpenAI Vision หรือโมเดลภาพใน Backend เพิ่มในขั้นถัดไป


## v1.3.2 Paste Upload
- รองรับการวางรูปภาพกราฟจาก Clipboard ด้วย Ctrl+V / Cmd+V
- รองรับ Drag & Drop และ Choose File เหมือนเดิม
- เมื่อ Paste รูป ระบบจะอัปโหลดเข้า `/api/chart-image/upload` อัตโนมัติ


## Paste Upload Fix v1.3.2
- รองรับการวางรูปด้วย Ctrl+V / Cmd+V แบบ robust มากขึ้น
- รองรับการ Copy รูปจาก Snipping Tool, Browser, TradingView Screenshot และไฟล์รูปจากเครื่อง
- เพิ่มปุ่ม Paste Image สำหรับ Browser ที่รองรับ Clipboard API
- แนะนำผู้ใช้: คลิกในกรอบอัปโหลด 1 ครั้ง แล้วกด Ctrl+V / Cmd+V


## v1.4 Vision AI Chart Analysis

เพิ่มการวิเคราะห์ภาพกราฟจริงผ่าน Vision AI เมื่อกดปุ่ม **Analyze Image with AI**

### Environment Variables เพิ่มเติม

```env
OPENAI_API_KEY=ใส่ API Key ของคุณ
OPENAI_VISION_MODEL=gpt-4o-mini
VISION_PROVIDER=openai
```

ถ้าไม่ตั้ง `OPENAI_API_KEY` ระบบยังใช้งานได้ แต่จะเป็นโหมด Context Analysis และจะแจ้งว่า Vision AI ยังไม่เปิดใช้งาน

### Flow การใช้งาน

1. Copy/Paste หรืออัปโหลดภาพกราฟ TradingView / MT5 / MT4
2. กด Analyze Image with AI
3. Backend จะส่งภาพ + numeric analysis ไปให้ Vision AI
4. ระบบอัปเดต Trade Plan, Action, Confirmation, Risk Notes และ Confidence Score

> คำเตือน: ระบบนี้เป็นเครื่องมือช่วยวิเคราะห์ ไม่ใช่คำแนะนำการลงทุนหรือการันตีกำไร
