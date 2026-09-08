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

import aiofiles
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
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

STUDIO_BACKEND = os.environ.get("STUDIO_BACKEND", os.environ.get("SUBMODULE_BACKEND", "local"))
MAGICLAYER_CORE_URL = os.environ.get("MAGICLAYER_CORE_URL", "")
MAGICLAYER_CORE_TOKEN = os.environ.get("MAGICLAYER_CORE_TOKEN", "")
BACKEND = create_backend(STUDIO_BACKEND, MAGICLAYER_CORE_URL, MAGICLAYER_CORE_TOKEN)

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
        forwarded_uri = request.headers.get("x-forwarded-uri") or request.headers.get("x-invoke-path") or request.headers.get("x-matched-path")
        if forwarded_uri:
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
        return _jobs.get(job_id)


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
    if not job:
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
    return {
        "status": "ok",
        "jobs_total": total,
        "jobs_running": running,
        "max_concurrent": MAX_CONCURRENT_JOBS,
        "slots_available": _pipeline_semaphore._value,
        "backend": BACKEND.name,
    }


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


@app.post("/api/process/{job_id}")
def start_processing(
    job_id: str,
    background_tasks: BackgroundTasks,
    pdf_dpi: int = 120,
    padding: int = 8,
    min_score: float = 0.50,
    dilate_kernel: int = 31,
    inpaint_radius: int = 5,
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
        raise HTTPException(404, "找不到此工作")
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress"),
        "filename": job.get("filename"),
        "params": job.get("params"),
        "size_mb": job.get("size_mb"),
    }


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "找不到此工作")
    if job.get("status") != "done":
        raise HTTPException(425, f"尚未完成：{job.get('status')}")

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
        raise HTTPException(404, "找不到此工作")
    if job.get("status") == "running":
        raise HTTPException(409, "處理中，無法刪除")
    _delete_job_data(job_id)
    return {"deleted": job_id}


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
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")
    pages = job.get("pages", [])
    if page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    bg = pages[page_index].get("background")
    if not bg or not Path(bg).exists():
        raise HTTPException(404, "背景圖不存在")
    return FileResponse(bg, media_type="image/png")


@app.get("/api/jobs/{job_id}/pages/{page_index}/source")
def page_source(job_id: str, page_index: int):
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")
    pages = job.get("pages", [])
    if page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    src = pages[page_index].get("source_image")
    if not src or not Path(src).exists():
        raise HTTPException(404, "原始圖不存在")
    return FileResponse(src, media_type="image/png")


@app.get("/api/jobs/{job_id}/pages/{page_index}/layers/{layer_index}")
def page_layer(job_id: str, page_index: int, layer_index: int):
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")
    pages = job.get("pages", [])
    if page_index >= len(pages):
        raise HTTPException(404, "找不到此頁")
    layer_files = pages[page_index].get("layer_files", [])
    if layer_index >= len(layer_files):
        raise HTTPException(404, "找不到此圖層")
    f = Path(layer_files[layer_index])
    if not f.exists():
        raise HTTPException(404, "圖層檔不存在")
    return FileResponse(str(f), media_type="image/png")


@app.get("/api/jobs/{job_id}/download")
def download_pptx(job_id: str, custom: bool = False):
    job = _get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "資料尚未就緒")

    if custom and job.get("rebuilt_pptx_custom"):
        pptx = job["rebuilt_pptx_custom"]
    else:
        pptx = job.get("rebuilt_pptx")

    if not pptx or not Path(pptx).exists():
        raise HTTPException(404, "PPTX 尚未產生")
    filename = Path(job["filename"]).stem + ("_custom" if custom else "_rebuilt") + ".pptx"
    return FileResponse(
        pptx,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web.backend.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
