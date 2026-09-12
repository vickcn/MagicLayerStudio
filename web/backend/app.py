"""
MagicLayerStudio Web Backend
FastAPI server wrapping document_pipeline for web UI.
Run: conda run -n lama uvicorn web.backend.app:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode

import aiofiles
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# ── Project root ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
JOBS_DIR = Path(os.environ.get("JOBS_DIR", "/tmp/web_jobs" if os.environ.get("VERCEL") else str(PROJECT_ROOT / "tmp" / "web_jobs")))
try:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    JOBS_DIR = Path("/tmp/web_jobs")
    JOBS_DIR.mkdir(parents=True, exist_ok=True)

# ── Import pipeline ───────────────────────────────────────────────────────────
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from web.backend.adapters import create_backend
from web.backend.core_client import CoreRequestError

STUDIO_BACKEND = os.environ.get("STUDIO_BACKEND", os.environ.get("SUBMODULE_BACKEND", "local"))
MAGICLAYER_CORE_URL = os.environ.get("MAGICLAYER_CORE_URL", "")
MAGICLAYER_CORE_TOKEN = os.environ.get("MAGICLAYER_CORE_TOKEN", "")
BACKEND = create_backend(STUDIO_BACKEND, MAGICLAYER_CORE_URL, MAGICLAYER_CORE_TOKEN)
UPLOAD_MODE = os.environ.get(
    "STUDIO_UPLOAD_MODE",
    "gcs" if os.environ.get("VERCEL") and BACKEND.name == "core_api" else "local",
).strip().lower()

# ── Concurrency control ───────────────────────────────────────────────────────
# 同時最多處理 N 個任務，避免壓垮系統（Cloud Run 可透過環境變數調整）
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
_pipeline_semaphore = threading.Semaphore(MAX_CONCURRENT_JOBS)

# ── Job TTL ───────────────────────────────────────────────────────────────────
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", str(24 * 3600)))  # 預設 24h

# ── Job state store ───────────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

ALLOWED_SUFFIXES = {".pptx", ".pdf", ".png", ".jpg", ".jpeg"}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="MagicLayerStudio API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def vercel_path_rewrite(request, call_next):
    raw_path = request.scope.get("path", "")
    if raw_path == "/api/index.py" or raw_path.startswith("/api/index.py"):
        query_pairs = parse_qsl(request.scope.get("query_string", b"").decode("utf-8"), keep_blank_values=True)
        forwarded_uri = request.headers.get("x-forwarded-uri") or request.headers.get("x-invoke-path") or request.headers.get("x-matched-path")
        forwarded_path = next((value for key, value in query_pairs if key == "__studio_path"), "")
        if forwarded_path:
            real_path = forwarded_path
            query_pairs = [(key, value) for key, value in query_pairs if key != "__studio_path"]
            request.scope["query_string"] = urlencode(query_pairs).encode("utf-8")
            request.scope["path"] = real_path if real_path.startswith("/") else ("/" + real_path)
        elif forwarded_uri:
            real_path = forwarded_uri.split("?")[0]
            request.scope["path"] = real_path if real_path.startswith("/") else ("/" + real_path)
        else:
            new_path = raw_path[13:]
            request.scope["path"] = new_path if new_path.startswith("/") else ("/" + new_path)
    return await call_next(request)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ── Helper ────────────────────────────────────────────────────────────────────
def _set_job(job_id: str, **kwargs):
    with _jobs_lock:
        if job_id not in _jobs:
            _jobs[job_id] = {}
        _jobs[job_id].update(kwargs)
    _persist_job_meta(job_id)


def _get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            return job
    meta_file = JOBS_DIR / job_id / "meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            with _jobs_lock:
                _jobs[job_id] = meta
            return meta
        except Exception:
            pass
    return None


def _delete_job_data(job_id: str):
    """從 state store 移除，並刪除磁碟上的工作目錄。"""
    job_dir = JOBS_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    with _jobs_lock:
        _jobs.pop(job_id, None)


def _cleanup_expired_jobs():
    """清除超過 TTL 的工作（每次收到請求時呼叫）。"""
    now = time.time()
    with _jobs_lock:
        expired = [
            jid for jid, job in _jobs.items()
            if now - job.get("created_at", now) > JOB_TTL_SECONDS
        ]
    for jid in expired:
        _delete_job_data(jid)


def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / 1024 / 1024, 1)


def _core_http_error(error: Exception, operation: str) -> HTTPException:
    """Translate Core failures without reflecting worker internals to browsers."""
    status_code = error.status_code if isinstance(error, CoreRequestError) else getattr(error, "code", 502)
    if operation == "complete_upload" and status_code == 404:
        detail = {
            "code": "upload_not_found",
            "message": "上傳暫存已失效或找不到，請重新上傳。",
            "retryable": False,
        }
        return HTTPException(status_code=404, detail=detail)
    if operation == "complete_upload" and status_code == 400:
        detail = {
            "code": "upload_validation_failed",
            "message": "上傳檔案驗證失敗，請重新選擇檔案。",
            "retryable": False,
        }
        return HTTPException(status_code=400, detail=detail)
    if operation == "complete_upload":
        detail = {
            "code": "core_job_state_unavailable",
            "message": "Core 暫時無法建立工作狀態，請稍後重試。",
            "retryable": True,
        }
        return HTTPException(status_code=503, detail=detail)
    return HTTPException(
        status_code=503,
        detail={
            "code": "core_unavailable",
            "message": "Core 服務暫時無法使用，請稍後重試。",
            "retryable": True,
        },
    )


def _remote_artifact_redirect(job_id: str, relative_path: str):
    if BACKEND.name != "core_api":
        raise HTTPException(404, "遠端檔案服務未啟用")
    try:
        signed_url = BACKEND.artifact_redirect(job_id, relative_path)
    except Exception as exc:
        raise _core_http_error(exc, "artifact") from exc
    if not signed_url:
        raise HTTPException(404, "檔案不存在或已過期")
    return RedirectResponse(url=signed_url, status_code=307)


def _remote_page_asset_redirect(job_id: str, page_index: int, field: str, layer_index: int = 0):
    try:
        result = BACKEND.get_result(job_id)
    except Exception as exc:
        raise _core_http_error(exc, "result") from exc
    pages = result.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    page = pages[page_index]
    if field == "layer_files":
        layer_files = page.get("layer_files") or []
        value = layer_files[layer_index] if 0 <= layer_index < len(layer_files) else None
    else:
        value = page.get(field)
    if not isinstance(value, str) or not value:
        raise HTTPException(404, "檔案不存在")
    return _remote_artifact_redirect(job_id, value)


def _run_pipeline(job_id: str, input_path: Path, output_dir: Path, options: PipelineOptions):
    """Run pipeline in background thread with semaphore guard."""
    acquired = _pipeline_semaphore.acquire(timeout=0)
    if not acquired:
        _set_job(job_id, status="error", progress=f"目前系統繁忙（最多同時 {MAX_CONCURRENT_JOBS} 個任務），請稍後再試")
        return

    try:
        _set_job(job_id, status="running", progress="處理中…", started_at=time.time())
        if BACKEND.name == "core_api":
            core_result = BACKEND.process(input_path, output_dir, options)
            _set_job(job_id, status="done", progress="完成", pages=core_result.get("pages", []),
                     output_dir=str(output_dir), finished_at=time.time())
            return
        result = BACKEND.process(input_path, output_dir, options)

        pages = []
        for page_result in result.pages:
            page_dir = page_result.output_dir
            bg_path = page_result.background_path
            text_layers_dir = page_dir / "text_layers"
            layer_files = sorted(text_layers_dir.glob("*.png")) if text_layers_dir.exists() else []

            # 讀取 layers.json 取得完整 layer 資訊（含 style_hint）
            layers_detail = []
            layers_json_path = page_result.layers_json
            if layers_json_path and Path(layers_json_path).exists():
                try:
                    with open(layers_json_path, "r", encoding="utf-8") as _f:
                        _layers_data = json.load(_f)
                    layers_detail = _layers_data.get("layers", [])
                except Exception:
                    pass

            pages.append({
                "page_id": page_result.page.id,
                "index": page_result.page.index,
                "source_image": str(page_result.page.image_path),
                "background": str(bg_path) if bg_path else None,
                "layers_json": str(page_result.layers_json),
                "objects_json": str(page_result.objects_json),
                "layer_count": len(layer_files),
                "layer_files": [str(f) for f in layer_files],
                "layers": layers_detail,  # 含 style_hint
            })

        rebuilt_pptx = str(result.rebuilt_pptx_path) if result.rebuilt_pptx_path else None
        size_mb = _dir_size_mb(output_dir)
        _set_job(
            job_id,
            status="done",
            progress="完成",
            pages=pages,
            rebuilt_pptx=rebuilt_pptx,
            output_dir=str(output_dir),
            size_mb=size_mb,
            finished_at=time.time(),
        )
    except Exception as exc:
        _set_job(job_id, status="error", progress=f"處理失敗：{exc}", error=str(exc))
    finally:
        _pipeline_semaphore.release()


# ── Startup: scan existing job dirs back into memory (Cloud Run restart-safe) ─
@app.on_event("startup")
def _restore_jobs_from_disk():
    """重啟後從磁碟掃描已存在的工作，恢復到 state store。"""
    for job_dir in JOBS_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        meta_file = job_dir / "meta.json"
        if meta_file.exists():
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                with _jobs_lock:
                    _jobs[job_dir.name] = meta
            except Exception:
                pass


def _persist_job_meta(job_id: str):
    """把 job 狀態寫到磁碟，供重啟後恢復。"""
    job = _get_job(job_id)
    if not job or job.get("remote_job_id"):
        return
    try:
        meta_file = JOBS_DIR / job_id / "meta.json"
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_file, "w") as f:
            json.dump(job, f, ensure_ascii=False, default=str)
    except Exception:
        pass


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    _cleanup_expired_jobs()
    return RedirectResponse(url="/app/", status_code=307)


@app.get("/api/health")
def health():
    with _jobs_lock:
        total = len(_jobs)
        running = sum(1 for j in _jobs.values() if j.get("status") == "running")
    result = {
        "status": "ok",
        "jobs_total": total,
        "jobs_running": running,
        "max_concurrent": MAX_CONCURRENT_JOBS,
        "slots_available": _pipeline_semaphore._value,
        "backend": BACKEND.name,
        "upload_mode": UPLOAD_MODE,
    }
    if BACKEND.name == "core_api":
        try:
            result["core_health"] = BACKEND.health().get("status")
        except Exception:
            result["core_health"] = "unreachable"
    return result


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    _cleanup_expired_jobs()
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"不支援的檔案格式：{suffix}。支援：{', '.join(ALLOWED_SUFFIXES)}")

    job_id = uuid.uuid4().hex
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)

    upload_path = job_dir / f"upload{suffix}"
    async with aiofiles.open(upload_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    _set_job(
        job_id,
        status="pending",
        progress="等待處理",
        filename=file.filename,
        upload_path=str(upload_path),
        created_at=time.time(),
    )
    _persist_job_meta(job_id)
    return {"job_id": job_id, "filename": file.filename}


@app.post("/api/upload/prepare")
def prepare_remote_upload(payload: Dict[str, Any], request: Request):
    """Request a short-lived Core/GCS upload URL without receiving file bytes."""
    if UPLOAD_MODE != "gcs" or BACKEND.name != "core_api":
        raise HTTPException(404, "目前環境使用本機上傳流程")
    filename = str(payload.get("filename") or "")
    if not filename:
        raise HTTPException(400, "缺少檔案名稱")
    _, session = resolve_google_session(request)
    requested_by = session.get("sub") if session else None
    owner_email = session.get("email") if session else None
    try:
        return BACKEND.prepare_upload(
            filename,
            str(payload.get("content_type") or "application/octet-stream"),
            payload.get("size"),
            requested_by=requested_by,
            owner_email=owner_email,
        )
    except Exception as exc:
        raise _core_http_error(exc, "prepare_upload") from exc


@app.post("/api/upload/{upload_id}/complete")
def complete_remote_upload(upload_id: str, payload: Dict[str, Any], request: Request):
    """Tell Core to verify the GCS object and start the heavy job."""
    if UPLOAD_MODE != "gcs" or BACKEND.name != "core_api":
        raise HTTPException(404, "目前環境使用本機上傳流程")
    _, session = resolve_google_session(request)
    requested_by = session.get("sub") if session else None
    owner_email = session.get("email") if session else None
    try:
        core_job = BACKEND.complete_upload(
            upload_id,
            payload.get("options") or {},
            payload.get("filename"),
            payload.get("size"),
            requested_by=requested_by,
            owner_email=owner_email,
        )
    except Exception as exc:
        raise _core_http_error(exc, "complete_upload") from exc

    job_id = core_job["job_id"]
    _set_job(
        job_id,
        status="pending",
        progress="已上傳至安全暫存，等待 Core 分析",
        filename=payload.get("filename") or "uploaded file",
        remote_job_id=job_id,
        created_at=time.time(),
        params=payload.get("options") or {},
    )
    return {"job_id": job_id, "status": "started"}


@app.post("/api/process/{job_id}")
def start_processing(
    job_id: str,
    background_tasks: BackgroundTasks,
    pdf_dpi: int = 120,
    padding: int = 8,
    min_score: float = 0.50,
    dilate_kernel: int = 3,
    inpaint_radius: int = 1,
    inpaint_backend: str = "telea",
    rebuild_pptx: bool = True,
):
    """Kick off background processing for a previously uploaded file."""
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "找不到此工作，請重新上傳")
    if job.get("status") == "running":
        raise HTTPException(409, "處理中，請稍候")

    input_path = Path(job["upload_path"])
    output_dir = JOBS_DIR / job_id / "output"
    output_dir.mkdir(exist_ok=True)

    from src.models.document import PipelineOptions

    options = PipelineOptions(
        pdf_dpi=pdf_dpi,
        padding=padding,
        min_score=min_score,
        dilate_kernel_size=dilate_kernel,
        inpaint_radius=inpaint_radius,
        inpaint_backend=inpaint_backend,
        rebuild_pptx=rebuild_pptx,
        debug_outputs=True,
    )

    _set_job(job_id, status="pending", progress="排程中", params={
        "pdf_dpi": pdf_dpi, "padding": padding, "min_score": min_score,
        "dilate_kernel": dilate_kernel, "inpaint_radius": inpaint_radius,
        "inpaint_backend": inpaint_backend,
    })

    background_tasks.add_task(_run_pipeline, job_id, input_path, output_dir, options)
    return {"job_id": job_id, "status": "started"}


@app.get("/api/jobs/{job_id}/status")
def job_status(job_id: str):
    job = _get_job(job_id)
    if not job:
        # Vercel instances are ephemeral. Remote Core owns the durable record,
        # so a cold/replaced Studio instance can still resume polling by ID.
        if BACKEND.name == "core_api":
            try:
                remote = BACKEND.get_status(job_id)
            except Exception as exc:
                raise HTTPException(502, "Core 狀態服務暫時無法使用") from exc
            status = {"queued": "pending", "running": "running", "completed": "done", "failed": "error", "cancelled": "error"}.get(remote.get("status", "queued"), "pending")
            return {
                "job_id": job_id,
                "status": status,
                "progress": remote.get("progress_text") or "處理中…",
                "filename": None,
                "params": None,
                "size_mb": None,
            }
        raise HTTPException(404, "找不到此工作")
    if job.get("remote_job_id") and BACKEND.name == "core_api":
        try:
            remote = BACKEND.get_status(job["remote_job_id"])
        except Exception as exc:
            raise HTTPException(502, "Core 狀態服務暫時無法使用") from exc
        remote_status = remote.get("status", "queued")
        status = {"queued": "pending", "running": "running", "completed": "done", "failed": "error", "cancelled": "error"}.get(remote_status, "pending")
        _set_job(job_id, status=status, progress=remote.get("progress_text") or "處理中…", error=remote.get("error"))
        job = _get_job(job_id) or job
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress"),
        "filename": job.get("filename"),
        "params": job.get("params"),
        "size_mb": job.get("size_mb"),
    }


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> Dict[str, Any]:
    job = _get_job(job_id)
    if not job:
        if BACKEND.name == "core_api":
            try:
                remote = BACKEND.cancel_remote_job(job_id)
            except Exception as exc:
                raise HTTPException(502, "Core 中止服務暫時無法使用") from exc
            return {"job_id": job_id, "status": remote.get("status", "cancelled")}
        raise HTTPException(404, "找不到此工作")
    if not job.get("remote_job_id") or BACKEND.name != "core_api":
        raise HTTPException(409, "目前只支援中止遠端 Core 工作")
    try:
        remote = BACKEND.cancel_remote_job(job["remote_job_id"])
    except Exception as exc:
        raise HTTPException(502, "Core 中止服務暫時無法使用") from exc
    _set_job(job_id, status="error", progress="已要求 Core 中止處理", error="cancelled")
    return {"job_id": job_id, "status": remote.get("status", "cancelled")}


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    job = _get_job(job_id)
    if not job:
        if BACKEND.name == "core_api":
            try:
                remote_result = BACKEND.get_result(job_id)
            except Exception as exc:
                raise HTTPException(502, "Core 結果服務暫時無法使用") from exc
            return {
                "job_id": job_id,
                "pages": remote_result.get("pages", []),
                "rebuilt_pptx": remote_result.get("rebuilt_pptx"),
                "custom_edits": {},
                "size_mb": None,
            }
        raise HTTPException(404, "找不到此工作")
    if job.get("status") != "done":
        raise HTTPException(425, f"尚未完成：{job.get('status')}")

    if job.get("remote_job_id") and BACKEND.name == "core_api":
        try:
            remote_result = BACKEND.get_result(job["remote_job_id"])
        except Exception as exc:
            raise HTTPException(502, "Core 結果服務暫時無法使用") from exc
        _set_job(job_id, pages=remote_result.get("pages", []), rebuilt_pptx=remote_result.get("rebuilt_pptx"))
        job = _get_job(job_id) or job

    # 讀取已存在的 custom_edits
    custom_edits = job.get("custom_edits")
    if not custom_edits:
        edits_path = JOBS_DIR / job_id / "custom_edits.json"
        if edits_path.exists():
            try:
                with open(edits_path, "r", encoding="utf-8") as f:
                    custom_edits = json.load(f)
            except Exception:
                custom_edits = {}

    return {
        "job_id": job_id,
        "pages": job.get("pages", []),
        "rebuilt_pptx": job.get("rebuilt_pptx"),
        "custom_edits": custom_edits or {},
        "size_mb": job.get("size_mb"),
    }


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    """刪除工作及所有暫存檔，釋放磁碟空間。"""
    job = _get_job(job_id)
    if not job:
        if BACKEND.name == "core_api":
            try:
                BACKEND.delete_remote_job(job_id)
            except Exception as exc:
                raise HTTPException(502, "Core 清理服務暫時無法使用") from exc
            return {"deleted": job_id}
        raise HTTPException(404, "找不到此工作")
    if job.get("status") == "running":
        raise HTTPException(409, "處理中，無法刪除")
    if job.get("remote_job_id") and BACKEND.name == "core_api":
        try:
            BACKEND.delete_remote_job(job["remote_job_id"])
        except Exception as exc:
            raise HTTPException(502, "Core 清理服務暫時無法使用") from exc
    _delete_job_data(job_id)
    return {"deleted": job_id}


@app.get("/api/jobs")
def list_jobs():
    """列出所有已有產出的工作清單。"""
    _cleanup_expired_jobs()
    with _jobs_lock:
        jobs_list = []
        for jid, jdata in _jobs.items():
            jobs_list.append({
                "job_id": jid,
                "filename": jdata.get("filename"),
                "status": jdata.get("status"),
                "finished_at": jdata.get("finished_at", 0),
                "page_count": len(jdata.get("pages", [])),
            })
        jobs_list.sort(key=lambda x: x.get("finished_at") or 0, reverse=True)
        return {"jobs": jobs_list}


@app.post("/api/jobs/{job_id}/save_custom")
async def save_custom_edits(job_id: str, edits: Dict[str, Any]):
    """
    儲存使用者在前端編輯的自訂物件設定（文字、字型、大小、粗體、顏色、座標、模式）。
    edits: {
      "0": {  # pageIndex
        "text_000": {
          "mode": "wordart"|"image_layer",
          "text": "自訂文字",
          "x": 100, "y": 200, "width": 300, "height": 80,
          "style": { "font_name": "Noto Sans TC", "font_size_pt": 24, "bold": true, "color_rgb": [255,255,255], "align": "center" }
        }
      }
    }
    """
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "找不到此工作")

    edits_file = JOBS_DIR / job_id / "custom_edits.json"
    try:
        with open(edits_file, "w", encoding="utf-8") as f:
            json.dump(edits, f, ensure_ascii=False, indent=2)
        _set_job(job_id, custom_edits=edits)
    except Exception as e:
        raise HTTPException(500, f"儲存失敗：{e}")

    return {"status": "ok", "job_id": job_id, "saved_pages": list(edits.keys())}


@app.post("/api/jobs/{job_id}/rebuild")
def rebuild_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    layer_modes: Optional[str] = None,  # 相容舊版 JSON
    global_mode: str = "image_layer",
):
    """
    以使用者的 custom_edits 與指定模式重新產生 PPTX。
    """
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "找不到此工作")
    if job.get("status") != "done":
        raise HTTPException(425, "工作尚未完成")

    output_dir = Path(job["output_dir"])
    document_json = output_dir.parent / "output" / "document.json"
    if not document_json.exists():
        candidates = list((JOBS_DIR / job_id).rglob("document.json"))
        if not candidates:
            raise HTTPException(404, "找不到 document.json，無法重建")
        document_json = candidates[0]

    custom_edits_file = JOBS_DIR / job_id / "custom_edits.json"
    custom_edits_data = None
    if custom_edits_file.exists():
        custom_edits_data = custom_edits_file

    pptx_out = JOBS_DIR / job_id / "output" / "rebuilt_custom.pptx"
    pptx_out.parent.mkdir(parents=True, exist_ok=True)

    def _do_rebuild():
        try:
            from src.pptx_rebuilder import rebuild_pptx_from_document
            _set_job(job_id, rebuild_status="running")
            rebuild_pptx_from_document(
                document_json_path=document_json,
                output_pptx_path=pptx_out,
                rebuild_mode=global_mode,
                custom_edits=custom_edits_data,
            )
            size_mb = _dir_size_mb(JOBS_DIR / job_id)
            _set_job(
                job_id,
                rebuild_status="done",
                rebuilt_pptx_custom=str(pptx_out),
                size_mb=size_mb,
            )
        except Exception as e:
            _set_job(job_id, rebuild_status="error", rebuild_error=str(e))

    background_tasks.add_task(_do_rebuild)
    return {"job_id": job_id, "status": "rebuilding", "output": str(pptx_out)}



@app.get("/api/storage")
def storage_info():
    """回傳暫存區總佔用量（方便 UI 顯示）。"""
    _cleanup_expired_jobs()
    total_mb = _dir_size_mb(JOBS_DIR) if JOBS_DIR.exists() else 0.0
    with _jobs_lock:
        job_count = len(_jobs)
    return {
        "jobs_dir": str(JOBS_DIR),
        "total_mb": total_mb,
        "job_count": job_count,
        "ttl_hours": JOB_TTL_SECONDS // 3600,
    }


@app.delete("/api/storage/cleanup")
def cleanup_all_expired():
    """手動觸發清理過期工作。"""
    _cleanup_expired_jobs()
    total_mb = _dir_size_mb(JOBS_DIR) if JOBS_DIR.exists() else 0.0
    return {"status": "ok", "remaining_mb": total_mb}


@app.get("/api/jobs/{job_id}/pages/{page_index}/background")
def page_background(job_id: str, page_index: int):
    if BACKEND.name == "core_api":
        return _remote_page_asset_redirect(job_id, page_index, "background")
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")
    pages = job.get("pages", [])
    if page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    bg = pages[page_index].get("background")
    if isinstance(bg, str) and bg.startswith(("http://", "https://")):
        return RedirectResponse(url=bg, status_code=307)
    if not bg:
        raise HTTPException(404, "背景圖不存在")
    bg_path = Path(bg)
    if not bg_path.is_absolute():
        bg_path = JOBS_DIR / job_id / bg
    if not bg_path.exists():
        raise HTTPException(404, f"背景圖不存在: {bg}")
    return FileResponse(str(bg_path), media_type="image/png")


@app.get("/api/jobs/{job_id}/pages/{page_index}/source")
def page_source(job_id: str, page_index: int):
    if BACKEND.name == "core_api":
        return _remote_page_asset_redirect(job_id, page_index, "source_image")
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")
    pages = job.get("pages", [])
    if page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    src = pages[page_index].get("source_image")
    if isinstance(src, str) and src.startswith(("http://", "https://")):
        return RedirectResponse(url=src, status_code=307)
    if not src:
        raise HTTPException(404, "原始圖不存在")
    src_path = Path(src)
    if not src_path.is_absolute():
        src_path = JOBS_DIR / job_id / src
    if not src_path.exists():
        raise HTTPException(404, "原始圖不存在")
    return FileResponse(str(src_path), media_type="image/png")


@app.get("/api/jobs/{job_id}/pages/{page_index}/layers/{layer_index}")
def page_layer(job_id: str, page_index: int, layer_index: int):
    if BACKEND.name == "core_api":
        return _remote_page_asset_redirect(job_id, page_index, "layer_files", layer_index)
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")
    pages = job.get("pages", [])
    if page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    layer_files = pages[page_index].get("layer_files", [])
    if layer_index >= len(layer_files):
        raise HTTPException(404, "找不到此圖層")
    layer = layer_files[layer_index]
    if isinstance(layer, str) and layer.startswith(("http://", "https://")):
        return RedirectResponse(url=layer, status_code=307)
    layer_path = Path(layer)
    if not layer_path.is_absolute():
        layer_path = JOBS_DIR / job_id / layer
    if not layer_path.exists():
        raise HTTPException(404, "圖層不存在")
    return FileResponse(str(layer_path), media_type="image/png")


@app.get("/api/jobs/{job_id}/artifacts/{artifact_path:path}")
def remote_artifact(job_id: str, artifact_path: str):
    """BFF-only redirect: browser receives a short-lived GCS URL, never a Core token."""
    return _remote_artifact_redirect(job_id, artifact_path)


@app.get("/api/jobs/{job_id}/download")
def download_pptx(job_id: str, custom: bool = False):
    if BACKEND.name == "core_api":
        if custom:
            raise HTTPException(409, "遠端工作尚不支援儲存自訂編輯版")
        try:
            result = BACKEND.get_result(job_id)
        except Exception as exc:
            raise _core_http_error(exc, "result") from exc
        rebuilt_pptx = result.get("rebuilt_pptx")
        if not isinstance(rebuilt_pptx, str) or not rebuilt_pptx:
            raise HTTPException(404, "PPTX 尚未產生")
        return _remote_artifact_redirect(job_id, rebuilt_pptx)
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")

    if custom and job.get("rebuilt_pptx_custom"):
        pptx = job["rebuilt_pptx_custom"]
    else:
        pptx = job.get("rebuilt_pptx")

    if isinstance(pptx, str) and pptx.startswith(("http://", "https://")):
        return RedirectResponse(url=pptx, status_code=307)
    if not pptx or not Path(pptx).exists():
        raise HTTPException(404, "PPTX 尚未產生")
    filename = Path(job["filename"]).stem + ("_custom" if custom else "_rebuilt") + ".pptx"
    return FileResponse(
        pptx,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )



# ── Google OAuth 2.0 Auth Module (Synced from audioStudio) ───────────────────
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_SCOPES = "https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email"
GOOGLE_SESSION_COOKIE = "magiclayer_google_session"
GOOGLE_OAUTH_STATE_COOKIE = "magiclayer_google_oauth_state"
GOOGLE_OAUTH_NEXT_COOKIE = "magiclayer_google_oauth_next"
GOOGLE_SESSION_COOKIE_MAX_AGE = 30 * 86400  # 30 days
GOOGLE_OAUTH_COOKIE_MAX_AGE = 600  # 10 minutes

_google_sessions: Dict[str, Dict[str, Any]] = {}
_google_sessions_lock = threading.Lock()


def google_oauth_enabled() -> bool:
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def missing_google_oauth_config() -> list[str]:
    missing = []
    if not GOOGLE_CLIENT_ID:
        missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET:
        missing.append("GOOGLE_CLIENT_SECRET")
    return missing


def sanitize_return_path(target: str) -> str:
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/app"
    return target


def google_redirect_uri(request: Request) -> str:
    configured = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return str(request.url_for("google_auth_callback"))


def google_token_request(data: dict[str, str]) -> dict[str, Any]:
    import urllib.parse
    import urllib.request

    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Google OAuth token request failed: {exc}") from exc


def google_fetch_profile(access_token: str) -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Google profile request failed: {exc}") from exc


def refresh_google_session(session_id: str, session: dict[str, Any]) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    refresh_token = str(session.get("refresh_token") or "").strip()
    if not refresh_token or not google_oauth_enabled():
        return session_id, session

    expires_at = float(session.get("expires_at") or 0.0)
    # 如果 Access Token 還有 5 分鐘以上才過期，無須刷新
    if expires_at - time.time() > 300:
        return session_id, session

    try:
        tokens = google_token_request(
            {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        )
        new_access_token = str(tokens.get("access_token") or "").strip()
        if new_access_token:
            session["access_token"] = new_access_token
            expires_in = int(tokens.get("expires_in") or 3600)
            session["expires_at"] = time.time() + expires_in
            if tokens.get("refresh_token"):
                session["refresh_token"] = str(tokens.get("refresh_token")).strip()
            with _google_sessions_lock:
                _google_sessions[session_id] = session
            return session_id, session
    except Exception as err:
        # 若 refresh 失敗（例如授權遭原廠撤銷），刪除此 Session
        with _google_sessions_lock:
            _google_sessions.pop(session_id, None)
        return None, None

    return session_id, session


def resolve_google_session(request: Request) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    session_id = str(request.cookies.get(GOOGLE_SESSION_COOKIE) or "").strip()
    if not session_id:
        return None, None
    with _google_sessions_lock:
        session = _google_sessions.get(session_id)
        if not session:
            return None, None
        session_copy = dict(session)
    return refresh_google_session(session_id, session_copy)


@app.get("/auth/google/start")
def google_auth_start(request: Request, next: str = "/app") -> RedirectResponse:
    if not google_oauth_enabled():
        raise HTTPException(503, "尚未設定 GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET")
    oauth_state = uuid.uuid4().hex
    redirect_uri = google_redirect_uri(request)
    target = sanitize_return_path(next)
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": oauth_state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    response = RedirectResponse(auth_url, status_code=307)
    response.set_cookie(GOOGLE_OAUTH_STATE_COOKIE, oauth_state, httponly=True, samesite="lax", max_age=GOOGLE_OAUTH_COOKIE_MAX_AGE)
    response.set_cookie(GOOGLE_OAUTH_NEXT_COOKIE, target, httponly=True, samesite="lax", max_age=GOOGLE_OAUTH_COOKIE_MAX_AGE)
    return response


@app.get("/auth/google/callback", name="google_auth_callback")
def google_auth_callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
) -> RedirectResponse:
    next_path = sanitize_return_path(request.cookies.get(GOOGLE_OAUTH_NEXT_COOKIE) or "/app")
    response = RedirectResponse(next_path, status_code=307)
    response.delete_cookie(GOOGLE_OAUTH_STATE_COOKIE)
    response.delete_cookie(GOOGLE_OAUTH_NEXT_COOKIE)
    if error:
        response.delete_cookie(GOOGLE_SESSION_COOKIE)
        return response
    expected_state = str(request.cookies.get(GOOGLE_OAUTH_STATE_COOKIE) or "").strip()
    if not expected_state or not state or state != expected_state:
        response.delete_cookie(GOOGLE_SESSION_COOKIE)
        return response
    try:
        tokens = google_token_request(
            {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": google_redirect_uri(request),
                "grant_type": "authorization_code",
            }
        )
        access_token = str(tokens.get("access_token") or "").strip()
        if not access_token:
            response.delete_cookie(GOOGLE_SESSION_COOKIE)
            return response
        profile = google_fetch_profile(access_token)
        session_id = str(request.cookies.get(GOOGLE_SESSION_COOKIE) or "").strip() or uuid.uuid4().hex
        expires_in = int(tokens.get("expires_in") or 3600)
        session_data = {
            "sub": str(profile.get("sub") or "").strip(),
            "name": str(profile.get("name") or "").strip(),
            "email": str(profile.get("email") or "").strip(),
            "picture": str(profile.get("picture") or "").strip(),
            "access_token": access_token,
            "refresh_token": str(tokens.get("refresh_token") or "").strip(),
            "expires_in": expires_in,
            "expires_at": time.time() + expires_in,
        }
        with _google_sessions_lock:
            _google_sessions[session_id] = session_data
    except Exception as oauth_err:
        response.delete_cookie(GOOGLE_SESSION_COOKIE)
        return response
    response.set_cookie(GOOGLE_SESSION_COOKIE, session_id, httponly=True, samesite="lax", max_age=GOOGLE_SESSION_COOKIE_MAX_AGE)
    return response


@app.post("/auth/google/logout")
def google_auth_logout(request: Request) -> JSONResponse:
    session_id = str(request.cookies.get(GOOGLE_SESSION_COOKIE) or "").strip()
    if session_id:
        with _google_sessions_lock:
            _google_sessions.pop(session_id, None)
    response = JSONResponse({"ok": True})
    response.delete_cookie(GOOGLE_SESSION_COOKIE)
    return response


@app.get("/api/auth/session")
def google_session_info(request: Request) -> dict[str, Any]:
    session_id, session = resolve_google_session(request)
    if not session_id or not session:
        return {
            "configured": google_oauth_enabled(),
            "authenticated": False,
            "missing": missing_google_oauth_config(),
        }
    return {
        "configured": google_oauth_enabled(),
        "authenticated": True,
        "missing": missing_google_oauth_config(),
        "sub": session.get("sub", ""),
        "name": session.get("name", ""),
        "email": session.get("email", ""),
        "picture": session.get("picture", ""),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.backend.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
