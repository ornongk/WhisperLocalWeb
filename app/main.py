import os
import json
import uuid
import time
import pathlib
import subprocess
import threading
import logging
import secrets
import tempfile
from typing import Optional, Literal, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor

import aiofiles
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer
from faster_whisper import WhisperModel
from pydantic import BaseModel

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

# ====== Data Models ======
class ConfigModel(BaseModel):
    model_id: str
    compute_type: str
    default_language: str
    default_task: str
    max_workers: int

class TranscriptionRequest(BaseModel):
    language: Optional[str] = ""
    task: str = "transcribe"
    model: Optional[str] = ""

# ====== Configuration Management ======
def load_config() -> Dict[str, Any]:
    """Load configuration with error handling."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # 設定の検証とデフォルト値の補完
                for key, default_value in DEFAULTS.items():
                    if key.lower() not in config:
                        config[key.lower()] = default_value
                return config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config: {e}")
    
    # デフォルト設定で新規作成
    cfg = {
        "model_id": DEFAULTS["MODEL_ID"], 
        "compute_type": DEFAULTS["COMPUTE_TYPE"],
        "default_language": DEFAULTS["DEFAULT_LANGUAGE"],
        "default_task": DEFAULTS["DEFAULT_TASK"],
        "max_workers": DEFAULTS["MAX_WORKERS"]
    }
    save_config(cfg)
    return cfg

def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration with atomic write."""
    try:
        temp_file = CONFIG_FILE.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        temp_file.replace(CONFIG_FILE)
        logger.info(f"Configuration saved: {cfg}")
    except IOError as e:
        logger.error(f"Failed to save config: {e}")
        raise HTTPException(status_code=500, detail="設定の保存に失敗しました")

# Global configuration
current_config = load_config()
current_model = None
model_lock = threading.Lock()

def get_whisper_model(model_id: str = None, compute_type: str = None) -> WhisperModel:
    """Get or reload Whisper model with thread safety."""
    global current_model, current_config
    
    # 引数が指定されていない場合は現在の設定を使用
    if model_id is None:
        model_id = current_config.get("model_id", DEFAULTS["MODEL_ID"])
    if compute_type is None:
        compute_type = current_config.get("compute_type", DEFAULTS["COMPUTE_TYPE"])
    
    with model_lock:
        # モデルの再読み込みが必要かチェック
        if (current_model is None or 
            getattr(current_model, '_model_id', None) != model_id or
            getattr(current_model, '_compute_type', None) != compute_type):
            
            logger.info(f"Loading Whisper model: {model_id} with {compute_type}")
            try:
                current_model = WhisperModel(model_id, compute_type=compute_type)
                # モデル情報を保存（デバッグ用）
                current_model._model_id = model_id
                current_model._compute_type = compute_type
                logger.info(f"Model loaded successfully: {model_id}")
            except Exception as e:
                logger.error(f"Failed to load model {model_id}: {e}")
                raise HTTPException(status_code=500, detail=f"モデル読み込みエラー: {e}")
    
    return current_model

# ====== Job Management ======
jobs_data = []

def load_jobs() -> List[Dict]:
    """Load jobs from file."""
    global jobs_data
    if LOGS_FILE.exists():
        try:
            with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                jobs_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load jobs: {e}")
            jobs_data = []
    return jobs_data

def save_jobs() -> None:
    """Save jobs to file."""
    try:
        with open(LOGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(jobs_data, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.error(f"Failed to save jobs: {e}")

def add_job(job_data: Dict) -> None:
    """Add new job to the list."""
    jobs_data.insert(0, job_data)  # 新しいものを先頭に
    save_jobs()

def update_job_status(job_id: str, status: str, **kwargs) -> None:
    """Update job status."""
    for job in jobs_data:
        if job["job_id"] == job_id:
            job["status"] = status
            job.update(kwargs)
            break
    save_jobs()

# ====== FastAPI App ======
app = FastAPI(title="Local Web Transcriber", description="ローカル音声・動画文字起こしサービス")

# Templates - 修正されたパス
templates = Jinja2Templates(directory="templates")

# Load jobs on startup
load_jobs()

# ====== API Endpoints ======

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse("settings.html", {"request": request})

# ====== 修正: ヘルスチェックエンドポイント追加 ======
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy", 
        "message": "WhisperLocal Web is running",
        "timestamp": time.time(),
        "model_loaded": current_model is not None
    }

@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    return current_config

@app.post("/api/config")
async def update_config(config: ConfigModel):
    """Update configuration."""
    global current_config, current_model
    
    try:
        # 新しい設定を辞書に変換
        new_config = config.dict()
        
        # 設定を保存
        save_config(new_config)
        current_config = new_config
        
        # モデルが変更された場合は現在のモデルをクリア（次回使用時に再読み込み）
        with model_lock:
            if (current_model is not None and 
                (getattr(current_model, '_model_id', None) != config.model_id or
                 getattr(current_model, '_compute_type', None) != config.compute_type)):
                current_model = None
                logger.info("Model cleared due to configuration change")
        
        return {"status": "success", "message": "設定が更新されました"}
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/models")
async def get_available_models():
    """Get list of available models."""
    models = [
        {"id": "tiny", "size": "39MB", "speed": "超高速", "accuracy": "低"},
        {"id": "base", "size": "74MB", "speed": "高速", "accuracy": "中"},
        {"id": "small", "size": "244MB", "speed": "中速", "accuracy": "中高"},
        {"id": "medium", "size": "769MB", "speed": "中速", "accuracy": "高"},
        {"id": "large-v2", "size": "1550MB", "speed": "低速", "accuracy": "最高"},
        {"id": "large-v3", "size": "1550MB", "speed": "低速", "accuracy": "最高"},
    ]
    return models

@app.get("/api/languages")
async def get_supported_languages():
    """Get list of supported languages."""
    languages = [
        {"code": "", "name": "自動検出"},
        {"code": "ja", "name": "日本語"},
        {"code": "en", "name": "英語"},
        {"code": "zh", "name": "中国語"},
        {"code": "ko", "name": "韓国語"},
        {"code": "es", "name": "スペイン語"},
        {"code": "fr", "name": "フランス語"},
        {"code": "de", "name": "ドイツ語"},
        {"code": "it", "name": "イタリア語"},
        {"code": "pt", "name": "ポルトガル語"},
        {"code": "ru", "name": "ロシア語"},
        {"code": "ar", "name": "アラビア語"},
        {"code": "hi", "name": "ヒンディー語"},
        {"code": "th", "name": "タイ語"},
        {"code": "vi", "name": "ベトナム語"},
    ]
    return languages

@app.post("/api/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form(""),
    task: str = Form("transcribe"),
    model: str = Form("")
):
    """Transcribe audio/video file."""
    
    # ファイル検証
    if not file.filename:
        raise HTTPException(status_code=400, detail="ファイルが選択されていません")
    
    file_ext = pathlib.Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"サポートされていないファイル形式: {file_ext}")
    
    # ジョブID生成
    job_id = str(uuid.uuid4())
    timestamp = time.time()
    
    # ジョブ情報作成
    job_data = {
        "job_id": job_id,
        "filename": file.filename,
        "language": language if language else None,
        "task": task,
        "model": model if model else current_config.get("model_id", "base"),
        "status": "processing",
        "created_at": timestamp,
        "file_size": 0
    }
    
    try:
        # ファイル保存
        upload_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
        content = await file.read()
        
        # ファイルサイズチェック
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="ファイルサイズが500MBを超えています")
        if len(content) < MIN_FILE_SIZE:
            raise HTTPException(status_code=400, detail="ファイルが小さすぎます")
        
        job_data["file_size"] = len(content)
        
        async with aiofiles.open(upload_path, 'wb') as f:
            await f.write(content)
        
        # ジョブをキューに追加
        add_job(job_data)
        
        # バックグラウンドで処理開始
        threading.Thread(
            target=process_transcription_background,
            args=(job_id, str(upload_path), language, task, model),
            daemon=True
        ).start()
        
        return {
            "job_id": job_id,
            "status": "processing",
            "message": "文字起こし処理を開始しました"
        }
        
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        update_job_status(job_id, "error", error_message=str(e))
        raise HTTPException(status_code=500, detail=str(e))

def process_transcription_background(job_id: str, file_path: str, language: str, task: str, model: str):
    """Background transcription processing."""
    try:
        logger.info(f"Starting transcription for job {job_id}")
        
        # 使用するモデルとパラメータを決定
        model_id = model if model else current_config.get("model_id", "base")
        compute_type = current_config.get("compute_type", "int8")
        
        # Whisperモデル取得
        whisper_model = get_whisper_model(model_id, compute_type)
        
        # 言語設定
        language_code = language if language else None
        
        # 文字起こし実行
        segments, info = whisper_model.transcribe(
            file_path,
            language=language_code,
            task=task,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # 結果をテキストに変換
        transcription_text = ""
        segments_data = []
        
        for segment in segments:
            segment_data = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            segments_data.append(segment_data)
            transcription_text += segment.text.strip() + "\n"
        
        # 結果を保存
        output_data = {
            "job_id": job_id,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "transcription": transcription_text.strip(),
            "segments": segments_data,
            "model_used": model_id,
            "task": task
        }
        
        output_path = OUTPUT_DIR / f"{job_id}.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        # テキストファイルも保存
        txt_path = OUTPUT_DIR / f"{job_id}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(transcription_text.strip())
        
        # ジョブステータス更新
        update_job_status(
            job_id, 
            "completed",
            completed_at=time.time(),
            output_path=str(output_path),
            txt_path=str(txt_path),
            detected_language=info.language,
            duration=info.duration
        )
        
        logger.info(f"Transcription completed for job {job_id}")
        
    except Exception as e:
        logger.error(f"Transcription failed for job {job_id}: {e}")
        update_job_status(job_id, "error", error_message=str(e))
    
    finally:
        # アップロードファイルを削除
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.error(f"Failed to delete upload file {file_path}: {e}")

@app.get("/api/jobs")
async def get_jobs():
    """Get job history."""
    return jobs_data

@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: str):
    """Get job details."""
    for job in jobs_data:
        if job["job_id"] == job_id:
            return job
    raise HTTPException(status_code=404, detail="ジョブが見つかりません")

@app.get("/api/jobs/{job_id}/download")
async def download_result(job_id: str):
    """Download transcription result."""
    for job in jobs_data:
        if job["job_id"] == job_id and job["status"] == "completed":
            txt_path = OUTPUT_DIR / f"{job_id}.txt"
            if txt_path.exists():
                return FileResponse(
                    path=str(txt_path),
                    filename=f"transcription_{job['filename']}.txt",
                    media_type="text/plain"
                )
    
    raise HTTPException(status_code=404, detail="結果ファイルが見つかりません")

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete job and its files."""
    global jobs_data
    
    job_found = False
    for i, job in enumerate(jobs_data):
        if job["job_id"] == job_id:
            # ファイル削除
            for path in [OUTPUT_DIR / f"{job_id}.json", OUTPUT_DIR / f"{job_id}.txt"]:
                try:
                    if path.exists():
                        path.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete file {path}: {e}")
            
            # ジョブ削除
            jobs_data.pop(i)
            job_found = True
            break
    
    if not job_found:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    
    save_jobs()
    return {"status": "success", "message": "ジョブが削除されました"}

@app.get("/api/status")
async def get_system_status():
    """Get system status."""
    return {
        "status": "running",
        "current_config": current_config,
        "model_loaded": current_model is not None,
        "active_jobs": len([j for j in jobs_data if j["status"] == "processing"]),
        "total_jobs": len(jobs_data)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
