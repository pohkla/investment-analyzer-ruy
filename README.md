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
