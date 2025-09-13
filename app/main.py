import os
import json
import uuid
import time
import pathlib
import subprocess
import threading
import logging
import secrets
from typing import Optional, Literal, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor

import aiofiles
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from faster_whisper import WhisperModel

# ====== Constants ======
ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.mp4', '.avi', '.mov', '.m4a', '.flac', '.ogg', '.webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
MIN_FILE_SIZE = 1024  # 1KB

# ====== Logging setup ======
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== Config & persistence ======
DEFAULTS = {
    "MODEL_ID": os.getenv("MODEL_ID", "base"),
    "COMPUTE_TYPE": os.getenv("COMPUTE_TYPE", "int8"),
    "DEFAULT_LANGUAGE": os.getenv("DEFAULT_LANGUAGE", "ja"),
    "DEFAULT_TASK": os.getenv("DEFAULT_TASK", "transcribe"),
    "MAX_WORKERS": int(os.getenv("MAX_WORKERS", "2")),
}

UPLOAD_DIR = pathlib.Path("/data/uploads")
OUTPUT_DIR = pathlib.Path("/data/outputs")
LOGS_DIR = pathlib.Path("/data/logs")
LOGS_FILE = LOGS_DIR / "jobs.json"
CONFIG_FILE = pathlib.Path("/data/config.json")

# Create directories with proper permissions
for d in (UPLOAD_DIR, OUTPUT_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)
    d.chmod(0o755)

def load_config() -> Dict[str, Any]:
    """Load configuration with error handling."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config: {e}")
    
    cfg = {
        "model_id": DEFAULTS["MODEL_ID"], 
        "compute_type": DEFAULTS["COMPUTE_TYPE"]
    }
    save_config(cfg)
    return cfg

def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration with atomic write."""
    try:
        temp_file = CONFIG_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        temp_file.replace(CONFIG_FILE)
        logger.info("Configuration saved successfully")
    except IOError as e:
        logger.error(f"Failed to save config: {e}")
        raise

config = load_config()

AVAILABLE_MODELS = [
    "tiny", "base", "small", "medium", 
    "large-v1", "large-v2", "large-v3", "distil-large-v3"
]

# ====== App setup ======
app = FastAPI(
    title="Local Web Transcriber (Model Switch + Logs)", 
    version="0.4.2",
    description="Secure local web transcriber with model switching capabilities"
)

STATIC_DIR = pathlib.Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(pathlib.Path(__file__).parent / "templates"))

# ====== Security ======
def validate_filename(filename: str) -> bool:
    """Validate filename for security."""
    if not filename or len(filename) > 255:
        return False
    
    # Check for path traversal attempts
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    
    # Check extension
    ext = pathlib.Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    # Remove potentially dangerous characters
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
    sanitized = ''.join(c if c in safe_chars else '_' for c in filename)
    return sanitized[:200]  # Limit length

async def validate_file(file: UploadFile) -> Tuple[bool, str]:
    """Validate uploaded file."""
    if not file.filename:
        return False, "No filename provided"
    
    if not validate_filename(file.filename):
        return False, "Invalid filename or extension"
    
    # Check file size (approximate)
    content = await file.read()
    file_size = len(content)
    
    if file_size < MIN_FILE_SIZE:
        return False, "File too small"
    if file_size > MAX_FILE_SIZE:
        return False, "File too large (max 500MB)"
    
    # Reset file pointer
    await file.seek(0)
    
    return True, "Valid"

# ====== Model cache & switching ======
_model_cache: Dict[str, Any] = {"id": None, "compute_type": None, "model": None}
_loading: Dict[str, Any] = {"in_progress": False, "target": None, "error": None}
_switch_lock = threading.Lock()

def get_model() -> WhisperModel:
    """Get current model with thread-safe caching."""
    current_id = config["model_id"]
    current_compute = config["compute_type"]
    
    if (_model_cache["model"] is None or 
        _model_cache["id"] != current_id or 
        _model_cache["compute_type"] != current_compute):
        
        logger.info(f"Loading model: {current_id} with compute type: {current_compute}")
        try:
            model = WhisperModel(current_id, device="auto", compute_type=current_compute)
            _model_cache.update({
                "model": model,
                "id": current_id,
                "compute_type": current_compute
            })
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
    
    return _model_cache["model"]

def _do_switch(target_id: str, compute_type: str) -> None:
    """Switch model in background thread."""
    global _model_cache
    try:
        logger.info(f"Switching to model: {target_id}")
        model = WhisperModel(target_id, device="auto", compute_type=compute_type)
        
        with _switch_lock:
            _model_cache = {
                "id": target_id, 
                "compute_type": compute_type, 
                "model": model
            }
            config["model_id"] = target_id
            config["compute_type"] = compute_type
            save_config(config)
        
        _loading.update({"in_progress": False, "target": None, "error": None})
        logger.info(f"Successfully switched to model: {target_id}")
        
    except Exception as e:
        error_msg = f"Model switch failed: {str(e)}"
        logger.error(error_msg)
        _loading.update({"in_progress": False, "error": error_msg})

def queue_switch(target_id: str, compute_type: Optional[str] = None) -> None:
    """Queue model switch with validation."""
    if _loading["in_progress"]:
        raise HTTPException(status_code=409, detail="Model switch already in progress")
    
    if target_id not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail="Invalid model ID")
    
    compute_type = compute_type or config.get("compute_type", DEFAULTS["COMPUTE_TYPE"])
    valid_compute_types = ["int8", "int8_float16", "int16", "float16", "float32"]
    if compute_type not in valid_compute_types:
        raise HTTPException(status_code=400, detail="Invalid compute type")
    
    _loading.update({"in_progress": True, "target": target_id, "error": None})
    thread = threading.Thread(target=_do_switch, args=(target_id, compute_type), daemon=True)
    thread.start()

# ====== Logs helpers ======
def load_logs() -> Dict[str, Dict[str, Any]]:
    """Load logs with error handling."""
    if not LOGS_FILE.exists():
        return {}
    
    try:
        with open(LOGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load logs: {e}")
        return {}

def save_logs(logs_data: Dict[str, Dict[str, Any]]) -> None:
    """Save logs with atomic write."""
    try:
        temp_file = LOGS_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(logs_data, f, ensure_ascii=False, indent=2)
        temp_file.replace(LOGS_FILE)
    except IOError as e:
        logger.error(f"Failed to save logs: {e}")

def upsert_log(job_id: str, data: Dict[str, Any]) -> None:
    """Update or insert log entry."""
    logs = load_logs()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    
    base_entry = logs.get(job_id, {
        "job_id": job_id, 
        "created_at": timestamp
    })
    base_entry.update(data)
    base_entry["updated_at"] = timestamp
    
    logs[job_id] = base_entry
    save_logs(logs)

# ====== Text processing ======
def normalize_newlines(text: str) -> str:
    """Normalize newline characters."""
    if not text:
        return ""
    # Convert CRLF/CR to LF, convert literal backslash-n to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\n", "\n")
    return text

def srt_caption_text(text: str) -> str:
    """Format text for SRT captions."""
    normalized = normalize_newlines(text)
    # For SRT, collapse to single line to avoid formatting issues
    return " ".join(line.strip() for line in normalized.splitlines() if line.strip())

def format_timestamp_srt(seconds: float) -> str:
    """Format timestamp for SRT format."""
    milliseconds = int((seconds - int(seconds)) * 1000)
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def format_timestamp_vtt(seconds: float) -> str:
    """Format timestamp for WebVTT format."""
    milliseconds = int((seconds - int(seconds)) * 1000)
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"

def segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    """Convert segments to SRT format."""
    lines = []
    for i, segment in enumerate(segments, start=1):
        lines.extend([
            str(i),
            f"{format_timestamp_srt(segment['start'])} --> {format_timestamp_srt(segment['end'])}",
            srt_caption_text(segment['text']),
            ""
        ])
    return "\n".join(lines)

def segments_to_vtt(segments: List[Dict[str, Any]]) -> str:
    """Convert segments to WebVTT format."""
    lines = ["WEBVTT", ""]
    for segment in segments:
        lines.extend([
            f"{format_timestamp_vtt(segment['start'])} --> {format_timestamp_vtt(segment['end'])}",
            normalize_newlines(segment["text"]).strip(),
            ""
        ])
    return "\n".join(lines)

def segments_to_text(segments: List[Dict[str, Any]]) -> str:
    """Convert segments to plain text."""
    return "\n".join(normalize_newlines(segment["text"]).strip() 
                    for segment in segments if segment.get("text"))

# ====== File operations ======
def get_audio_duration(file_path: pathlib.Path) -> float:
    """Get audio/video duration using ffprobe."""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(file_path)
        ], capture_output=True, text=True, check=True, timeout=30)
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError, TypeError) as e:
        logger.warning(f"Could not determine duration for {file_path}: {e}")
        return 0.0

def cleanup_old_files(max_age_hours: int = 24) -> None:
    """Clean up old uploaded files."""
    cutoff_time = time.time() - (max_age_hours * 3600)
    
    for directory in [UPLOAD_DIR, OUTPUT_DIR]:
        try:
            for file_path in directory.iterdir():
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    logger.info(f"Cleaned up old file: {file_path}")
        except OSError as e:
            logger.error(f"Error during cleanup of {directory}: {e}")

# ====== Job processing ======
JOBS: Dict[str, Dict[str, Any]] = {}
EXECUTOR = ThreadPoolExecutor(max_workers=DEFAULTS["MAX_WORKERS"])

def transcribe_job(job_id: str, source_path: pathlib.Path, language: Optional[str], task: str) -> None:
    """Main transcription job function."""
    job_state = JOBS[job_id]
    job_state.update({
        "status": "running", 
        "progress": 0.0, 
        "segments": [], 
        "error": None
    })
    upsert_log(job_id, {"status": "running"})
    
    try:
        # Get file duration
        duration = get_audio_duration(source_path)
        job_state["duration"] = duration
        logger.info(f"Processing file {source_path} (duration: {duration}s)")
        
        # Get model and transcribe
        model = get_model()
        segments_iter, info = model.transcribe(
            str(source_path),
            language=language or DEFAULTS["DEFAULT_LANGUAGE"],
            task=task,
            vad_filter=True,  # Enable VAD for better segmentation
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False  # Reduce hallucinations
        )
        
        # Process segments
        all_segments = []
        last_end_time = 0.0
        
        for segment in segments_iter:
            segment_data = {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text
            }
            all_segments.append(segment_data)
            last_end_time = segment_data["end"]
            
            # Update progress
            if duration > 0:
                progress = min(last_end_time / duration, 0.99)
                job_state["progress"] = progress
                
            # Keep only recent segments in memory
            job_state["segments"] = all_segments[-50:]
        
        # Generate output files
        plain_text = segments_to_text(all_segments)
        srt_content = segments_to_srt(all_segments)
        vtt_content = segments_to_vtt(all_segments)
        
        # Write output files
        output_files = {}
        for ext, content in [("txt", plain_text), ("srt", srt_content), ("vtt", vtt_content)]:
            output_path = OUTPUT_DIR / f"{job_id}.{ext}"
            output_path.write_text(content, encoding="utf-8")
            output_files[ext] = f"/api/download/{job_id}.{ext}"
        
        # Write metadata
        metadata = {
            "language": info.language,
            "language_probability": getattr(info, "language_probability", None),
            "duration": duration,
            "model_id": config["model_id"],
            "compute_type": config["compute_type"],
            "task": task
        }
        
        json_data = {
            "meta": metadata,
            "segments": all_segments
        }
        json_path = OUTPUT_DIR / f"{job_id}.json"
        json_path.write_text(
            json.dumps(json_data, ensure_ascii=False, indent=2), 
            encoding="utf-8"
        )
        output_files["json"] = f"/api/download/{job_id}.json"
        
        # Update job state
        job_state.update({
            "status": "done",
            "progress": 1.0,
            "output_files": output_files,
            "preview": plain_text[:2000],
            "language": metadata["language"],
            "language_probability": metadata["language_probability"]
        })
        
        # Log completion
        upsert_log(job_id, {
            "status": "done",
            "filename": job_state.get("filename"),
            "duration": duration,
            "language": metadata["language"],
            "output_files": output_files,
            "task": task,
            "model_id": metadata["model_id"],
            "compute_type": metadata["compute_type"]
        })
        
        logger.info(f"Job {job_id} completed successfully")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed: {error_msg}")
        job_state.update({"status": "error", "error": error_msg})
        upsert_log(job_id, {"status": "error", "error": error_msg})
    
    finally:
        # Clean up uploaded file
        try:
            if source_path.exists():
                source_path.unlink()
                logger.info(f"Cleaned up uploaded file: {source_path}")
        except OSError as e:
            logger.error(f"Failed to clean up {source_path}: {e}")

# ====== Routes ======
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_page(request: Request, job_id: str):
    """Job status page."""
    # Validate job_id format
    try:
        uuid.UUID(job_id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    logs = load_logs()
    filename = logs.get(job_id, {}).get("filename", "")
    
    return templates.TemplateResponse("job.html", {
        "request": request, 
        "job_id": job_id, 
        "filename": filename
    })

@app.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    task: Literal["transcribe", "translate"] = Form(DEFAULTS["DEFAULT_TASK"])
):
    """Handle file upload and start transcription."""
    if _loading["in_progress"]:
        raise HTTPException(
            status_code=423, 
            detail="Model is switching. Please retry in a moment."
        )
    
    # Validate file
    is_valid, error_msg = await validate_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Generate job ID and prepare file
    job_id = uuid.uuid4().hex
    original_filename = file.filename
    safe_filename = sanitize_filename(original_filename)
    dest_path = UPLOAD_DIR / f"{job_id}_{safe_filename}"
    
    try:
        # Save uploaded file
        async with aiofiles.open(dest_path, "wb") as dest_file:
            while chunk := await file.read(8192):  # Read in chunks
                await dest_file.write(chunk)
        
        logger.info(f"File uploaded: {original_filename} -> {dest_path}")
        
        # Initialize job
        JOBS[job_id] = {
            "status": "queued",
            "progress": 0.0,
            "filename": original_filename,
            "segments": [],
            "preview": "",
            "output_files": {}
        }
        
        upsert_log(job_id, {
            "status": "queued",
            "filename": original_filename,
            "task": task,
            "model_id": config["model_id"],
            "compute_type": config["compute_type"]
        })
        
        # Submit job to executor
        EXECUTOR.submit(transcribe_job, job_id, dest_path, language, task)
        
        return templates.TemplateResponse("job.html", {
            "request": request,
            "job_id": job_id,
            "filename": original_filename
        })
        
    except Exception as e:
        # Clean up on error
        if dest_path.exists():
            dest_path.unlink()
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")

@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """Get job status."""
    # Validate job_id format
    try:
        uuid.UUID(job_id, version=4)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    # Check active jobs first
    if job_id in JOBS:
        job_state = JOBS[job_id]
        preview = job_state.get("preview") or "\n".join(
            normalize_newlines(seg.get("text", "")) 
            for seg in job_state.get("segments", [])
        )[:2000]
        
        return JSONResponse({
            "status": job_state.get("status"),
            "progress": round(float(job_state.get("progress", 0.0)), 4),
            "filename": job_state.get("filename"),
            "duration": job_state.get("duration"),
            "language": job_state.get("language"),
            "language_probability": job_state.get("language_probability"),
            "preview": preview,
            "output_files": job_state.get("output_files", {}),
            "error": job_state.get("error")
        })
    
    # Check completed jobs
    metadata_path = OUTPUT_DIR / f"{job_id}.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            txt_path = OUTPUT_DIR / f"{job_id}.txt"
            preview = ""
            if txt_path.exists():
                preview = normalize_newlines(
                    txt_path.read_text(encoding="utf-8")
                )[:2000]
            
            logs = load_logs()
            filename = logs.get(job_id, {}).get("filename", "")
            
            return JSONResponse({
                "status": "done",
                "progress": 1.0,
                "filename": filename,
                "duration": data.get("meta", {}).get("duration"),
                "language": data.get("meta", {}).get("language"),
                "language_probability": data.get("meta", {}).get("language_probability"),
                "preview": preview,
                "output_files": {
                    "txt": f"/api/download/{job_id}.txt",
                    "srt": f"/api/download/{job_id}.srt",
                    "vtt": f"/api/download/{job_id}.vtt",
                    "json": f"/api/download/{job_id}.json"
                },
                "error": None
            })
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading job metadata: {e}")
    
    # Check logs for job history
    logs = load_logs()
    if job_id in logs:
        log_entry = logs[job_id]
        return JSONResponse({
            "status": log_entry.get("status", "unknown"),
            "progress": 0.0,
            "filename": log_entry.get("filename"),
            "duration": log_entry.get("duration"),
            "language": log_entry.get("language"),
            "language_probability": None,
            "preview": "",
            "output_files": log_entry.get("output_files", {}),
            "error": log_entry.get("error")
        })
    
    raise HTTPException(status_code=404, detail="Job not found")

@app.get("/api/logs")
async def get_logs(limit: int = 50):
    """Get job logs."""
    if limit <= 0 or limit > 1000:
        limit = 50
    
    logs = load_logs()
    items = list(logs.values())
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    
    return JSONResponse(items[:limit])

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download output file."""
    # Validate filename
    if not filename or '..' in filename or '/' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    file_path = OUTPUT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        if filename.endswith(".json"):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return JSONResponse(data)
        else:
            # For text files, ensure proper newline handling
            content = file_path.read_text(encoding="utf-8")
            # Normalize any escaped newlines to actual newlines
            content = content.replace("\\n", "\n")
            return PlainTextResponse(content)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error serving file {filename}: {e}")
        raise HTTPException(status_code=500, detail="Error reading file")

# ====== Model management APIs ======
@app.get("/api/models")
async def list_models():
    """List available models."""
    return JSONResponse({
        "available": AVAILABLE_MODELS,
        "current": {
            "model_id": config["model_id"],
            "compute_type": config["compute_type"]
        },
        "loading": _loading
    })

@app.get("/api/model")
async def get_current_model():
    """Get current model status."""
    return JSONResponse({
        "current": {
            "model_id": config["model_id"],
            "compute_type": config["compute_type"]
        },
        "loading": _loading
    })

@app.post("/api/model")
async def switch_model(request: Request):
    """Switch to different model."""
    if _loading["in_progress"]:
        raise HTTPException(status_code=409, detail="Model switch already in progress")
    
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    target_model = body.get("id")
    compute_type = body.get("compute_type") or config.get("compute_type", DEFAULTS["COMPUTE_TYPE"])
    
    if not target_model:
        raise HTTPException(status_code=400, detail="Missing model ID")
    
    queue_switch(target_model, compute_type)
    
    return JSONResponse({
        "ok": True,
        "queued": {
            "id": target_model,
            "compute_type": compute_type
        }
    })

# ====== Startup/Shutdown events ======
@app.on_event("startup")
async def startup_event():
    """Application startup."""
    logger.info("Starting Local Web Transcriber")
    
    # Clean up old files on startup
    cleanup_old_files()
    
    # Validate initial model
    try:
        get_model()
        logger.info(f"Initial model loaded: {config['model_id']}")
    except Exception as e:
        logger.error(f"Failed to load initial model: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown."""
    logger.info("Shutting down Local Web Transcriber")
    EXECUTOR.shutdown(wait=True)

# ====== Health check ======
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "model_loaded": _model_cache["model"] is not None,
        "current_model": config["model_id"],
        "loading": _loading["in_progress"]
    })
