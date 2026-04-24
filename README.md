# Ray Investment Chart Analyzer

เว็บ Python + FastAPI สำหรับ Upload รูปกราฟ แล้ววิเคราะห์แนวโน้มเบื้องต้น

## Files

- `app.py` ไฟล์หลักของเว็บ
- `requirements.txt` รายการ Python package
- `render.yaml` ตั้งค่า Deploy บน Render

## Local run

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

เปิดเว็บ:

```text
http://127.0.0.1:8000
```

## Deploy on Render

1. สร้าง GitHub repository
2. Upload ไฟล์ทั้งหมดขึ้น GitHub
3. เข้า Render
4. New → Web Service
5. Connect GitHub repo
6. Render จะอ่าน `render.yaml` ให้อัตโนมัติ
7. Deploy
