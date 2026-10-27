import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.audio_processor import convert_to_wav, auto_transcribe
from core.voice_engine import VoiceCloneEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="VoiceClone Studio", description="Zero-Shot Neural Voice Cloning Web Studio")

# Global engine instance (lazy initialized)
engine = None
jobs = {}

def get_engine():
    global engine
    if engine is None:
        engine = VoiceCloneEngine()
    return engine

@app.post("/api/upload_voice")
async def upload_voice(file: UploadFile = File(...)):
    """Uploads a voice sample (1-2 minutes) and auto-transcribes it."""
    voice_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(file.filename)[1] or ".wav"
    raw_path = os.path.join(UPLOADS_DIR, f"{voice_id}_raw{ext}")
    clean_wav = os.path.join(UPLOADS_DIR, f"{voice_id}_clean.wav")

    content = await file.read()
    with open(raw_path, "wb") as f:
        f.write(content)

    # Convert to 24kHz Mono WAV
    convert_to_wav(raw_path, clean_wav, sample_rate=24000)

    # Auto-transcribe using local Whisper
    transcript = auto_transcribe(clean_wav)

    return {
        "voice_id": voice_id,
        "filename": file.filename,
        "transcript": transcript,
        "audio_url": f"/api/audio/upload/{voice_id}_clean.wav"
    }

class GenerateRequest(BaseModel):
    voice_id: str
    ref_text: str
    script_text: str
    speed: float = 1.40

def run_synthesis(job_id: str, voice_id: str, ref_text: str, script_text: str, speed: float):
    try:
        jobs[job_id]["status"] = "processing"
        eng = get_engine()
        ref_path = os.path.join(UPLOADS_DIR, f"{voice_id}_clean.wav")
        
        def update_progress(curr, total, msg):
            jobs[job_id]["progress"] = int((curr / total) * 100)
            jobs[job_id]["message"] = msg

        result = eng.generate_narration(
            ref_audio_path=ref_path,
            ref_text=ref_text,
            script_text=script_text,
            output_dir=OUTPUTS_DIR,
            job_id=job_id,
            speed=speed,
            progress_callback=update_progress
        )

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["progress"] = 100
        jobs[job_id]["duration"] = result["duration"]
        jobs[job_id]["wav_url"] = f"/api/download/{job_id}/wav"
        jobs[job_id]["mp3_url"] = f"/api/download/{job_id}/mp3"
        jobs[job_id]["message"] = f"Complete! ({result['duration']:.2f}s)"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)

@app.post("/api/generate")
async def generate_audio(req: GenerateRequest, background_tasks: BackgroundTasks):
    """Triggers voice cloning generation in background task."""
    ref_path = os.path.join(UPLOADS_DIR, f"{req.voice_id}_clean.wav")
    if not os.path.exists(ref_path):
        return JSONResponse({"error": "Voice sample not found. Please upload first."}, status_code=400)

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Initializing neural synthesis...",
        "job_id": job_id
    }

    background_tasks.add_task(
        run_synthesis, job_id, req.voice_id, req.ref_text, req.script_text, req.speed
    )

    return {"job_id": job_id, "status": "queued"}

@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return job

@app.get("/api/download/{job_id}/{fmt}")
async def download_file(job_id: str, fmt: str):
    filename = f"{job_id}.{fmt}"
    file_path = os.path.join(OUTPUTS_DIR, filename)
    if not os.path.exists(file_path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    media_type = "audio/wav" if fmt == "wav" else "audio/mpeg"
    return FileResponse(file_path, media_type=media_type, filename=filename)

@app.get("/api/audio/upload/{filename}")
async def get_uploaded_audio(filename: str):
    file_path = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(file_path):
        return JSONResponse({"error": "Audio not found"}, status_code=404)
    return FileResponse(file_path, media_type="audio/wav")

# Mount Static UI
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("\n🌟 Starting VoiceClone Studio on http://127.0.0.1:7860...")
    uvicorn.run("app:app", host="127.0.0.1", port=7860, reload=False)
