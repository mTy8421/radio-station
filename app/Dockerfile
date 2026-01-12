FROM python:3.9-slim

# ติดตั้ง FFmpeg (หัวใจสำคัญในการ Stream เสียง)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency และ install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY main.py .

# สร้างโฟลเดอร์ music รอไว้ (เผื่อ volume ไม่ mount)
RUN mkdir -p /app/music

# รัน FastAPI (API) และ Background Thread (DJ) พร้อมกัน
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]

