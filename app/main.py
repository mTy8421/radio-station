import json
import os
import random
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

# --- Configuration ---
MUSIC_DIR = "/app/music"
DB_FILE = "/app/music/metadata.json"  # เก็บข้อมูลเวลาเล่นเพลงที่นี่
ICECAST_URL = f"icecast://source:{os.getenv('ICECAST_PASSWORD')}@{os.getenv('ICECAST_HOST')}:{os.getenv('ICECAST_PORT')}{os.getenv('ICECAST_MOUNT')}"

app = FastAPI()


# --- Helper Functions ---
def load_metadata():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_metadata(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


# --- DJ Logic (Background Thread) ---
def stream_file(filepath):
    """ใช้ FFmpeg ส่งไฟล์ไปยัง Icecast"""
    print(f"Adding to queue: {filepath}")
    # คำสั่ง FFmpeg สำหรับ Stream ไฟล์เดียวแล้วจบ (เพื่อให้ Python เลือกไฟล์ใหม่ต่อได้)
    command = [
        "ffmpeg",
        "-re",  # Read input at native frame rate
        "-i",
        filepath,
        "-c:a",
        "libmp3lame",  # Encode เป็น MP3
        "-b:a",
        "128k",  # Bitrate
        "-content_type",
        "audio/mpeg",
        "-f",
        "mp3",
        ICECAST_URL,
    ]

    # รัน FFmpeg และรอจนกว่าเพลงจะจบ
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error streaming {filepath}: {e}")
        time.sleep(1)  # กัน Loop รัวเวลามี error


def dj_loop():
    """ลูปทำงานตลอด 24 ชม."""
    print("DJ System Started...")
    # รอให้ Icecast boot เสร็จก่อนเล็กน้อย
    time.sleep(5)

    while True:
        metadata = load_metadata()
        files = [f for f in os.listdir(MUSIC_DIR) if f.endswith(".mp3")]

        if not files:
            print("No music files found. Sleeping 10s...")
            time.sleep(10)
            continue

        valid_songs = []
        current_hour = datetime.now().hour

        # Logic กรองเพลงตามช่วงเวลา
        for file in files:
            meta = metadata.get(file, {})
            start = meta.get("start_hour")
            end = meta.get("end_hour")

            # ถ้าไม่มีการกำหนดเวลา ให้เล่นได้ตลอด
            if start is None or end is None:
                valid_songs.append(file)
            else:
                # ตรวจสอบช่วงเวลา (รองรับข้ามคืน เช่น 22:00 - 02:00)
                if start <= end:
                    if start <= current_hour < end:
                        valid_songs.append(file)
                else:  # กรณีข้ามวัน
                    if current_hour >= start or current_hour < end:
                        valid_songs.append(file)

        if not valid_songs:
            print(
                f"No valid songs for current hour ({current_hour}). Playing fallback/random if any."
            )
            # fallback: ถ้าไม่มีเพลงตรงเงื่อนไขเลย ให้สุ่มจากไฟล์ทั้งหมด (หรือจะให้เงียบก็ได้)
            current_song = random.choice(files)
        else:
            current_song = random.choice(valid_songs)

        # เริ่มเล่นเพลง
        full_path = os.path.join(MUSIC_DIR, current_song)
        stream_file(full_path)
        # เมื่อ stream_file จบ (เพลงจบ) ลูปจะหมุนใหม่เพื่อเลือกเพลงถัดไปทันที


# Start DJ Loop in Background
threading.Thread(target=dj_loop, daemon=True).start()

# --- API Endpoints ---


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    start_hour: Optional[int] = Form(None),
    end_hour: Optional[int] = Form(None),
):
    """อัปโหลดเพลง พร้อมกำหนดเวลาเล่น (ชั่วโมง 0-23)"""
    file_location = os.path.join(MUSIC_DIR, file.filename)
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())

    # Update Metadata
    metadata = load_metadata()
    metadata[file.filename] = {"start_hour": start_hour, "end_hour": end_hour}
    save_metadata(metadata)

    return {
        "info": f"file '{file.filename}' saved",
        "schedule": f"{start_hour}-{end_hour}",
    }


@app.get("/playlist")
def get_playlist():
    return load_metadata()


@app.delete("/delete/{filename}")
def delete_file(filename: str):
    file_path = os.path.join(MUSIC_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)

        metadata = load_metadata()
        if filename in metadata:
            del metadata[filename]
            save_metadata(metadata)

        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="File not found")
