# Ray Local Investment Analyzer v6

เว็บวิเคราะห์ภาพกราฟแบบรันบนเครื่อง local โดยไม่ใช้ฐานข้อมูล

## ความสามารถใน v6
- อัปโหลดภาพได้หลายไฟล์
- รองรับการ Paste ภาพจาก Clipboard ด้วย Ctrl+V
- อ่าน Symbol จากภาพ
- อ่าน Timeframe จากภาพ
- OCR ราคาจากภาพ
- ประเมินแนวโน้มจากภาพกราฟ
- แยกแท่งเทียนแบบละเอียดขึ้น
- อ่าน Trendline / Breakout / Liquidity Zone
- คำนวณ Entry / Stop Loss / TP1 / TP2
- Export รายงาน HTML สวย ๆ บน local

## เทคโนโลยี
- FastAPI
- OpenCV
- Pillow
- pytesseract
- HTML/CSS/JavaScript ฝั่งหน้าเว็บ

## วิธีรัน
### Windows
1. แตก zip
2. ติดตั้ง Python 3.10+
3. ติดตั้ง Tesseract OCR และให้คำสั่ง `tesseract` ใช้งานได้ใน PATH
4. ดับเบิลคลิก `run_local.bat`
5. เปิด `http://127.0.0.1:8000`

### macOS / Linux
1. แตก zip
2. ติดตั้ง Python 3.10+
3. ติดตั้ง Tesseract OCR และให้คำสั่ง `tesseract` ใช้งานได้ใน PATH
4. รัน `bash run_local.sh`
5. เปิด `http://127.0.0.1:8000`

## หมายเหตุสำคัญ
- รุ่นนี้ยังเป็น OCR + heuristic vision engine ไม่ใช่ deep learning model เต็มรูปแบบ
- ความแม่นขึ้นอยู่กับความชัดของภาพ, การครอป, สีธีมกราฟ, และการเห็นแกนราคาชัดเจน
- ควรใช้ผลลัพธ์เป็นเครื่องมือช่วยตัดสินใจ ไม่ใช่คำสั่งซื้อขายอัตโนมัติ

## แนวทางต่อยอด
- แยกสีแท่งเขียว/แดงจากธีมกราฟแบบเฉพาะแพลตฟอร์ม
- เพิ่ม OCR โซนราคาเฉพาะแกนขวาให้แม่นขึ้น
- เพิ่ม deep learning vision model สำหรับ candlestick segmentation
- Export เป็น PDF เพิ่มเติม
