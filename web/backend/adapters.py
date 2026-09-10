"""Backend adapters used by MagicLayerStudio.

The Studio contract stays the same while the implementation can be switched
between the local pipeline and MagicLayerCore's HTTP API by configuration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


class LocalCoreBackend:
    name = "local"

    def process(self, input_path: Path, output_dir: Path, options: Any) -> Any:
        # Import lazily so a Core API deployment does not need OCR/torch deps.
        from src.pipeline.document_pipeline import process_document

        return process_document([input_path], output_dir, options)


class RemoteCoreBackend:
    name = "core_api"

    def __init__(self, base_url: str, token: str = "", timeout: int = 30):
        from web.backend.core_client import MagicLayerCoreClient

        self.client = MagicLayerCoreClient(base_url, token=token, timeout=timeout)

    def process(self, input_path: Path, output_dir: Path, options: Any) -> dict:
        params = {
            "pdf_dpi": options.pdf_dpi,
            "padding": options.padding,
            "min_score": options.min_score,
            "dilate_kernel_size": options.dilate_kernel_size,
            "inpaint_radius": options.inpaint_radius,
            "inpaint_backend": options.inpaint_backend,
            "rebuild_pptx": options.rebuild_pptx,
            "debug_outputs": options.debug_outputs,
        }
        return self.client.submit_and_wait(input_path, output_dir, params)

    def prepare_upload(self, filename: str, content_type: str, size: Optional[int]) -> dict:
        return self.client.prepare_upload(filename, content_type, size)

    def complete_upload(self, upload_id: str, options: dict, filename: Optional[str] = None, size: Optional[int] = None) -> dict:
        return self.client.complete_upload(upload_id, options, filename, size)

    def get_status(self, job_id: str) -> dict:
        return self.client.get_job(job_id)

    def health(self) -> dict:
        return self.client.health()

    def get_result(self, job_id: str) -> dict:
        return self.client.result(job_id)

    def delete_remote_job(self, job_id: str) -> dict:
        return self.client.delete_job(job_id)

    def cancel_remote_job(self, job_id: str) -> dict:
        return self.client.cancel_job(job_id)

    def artifact_redirect(self, job_id: str, relative_path: str) -> Optional[str]:
        return self.client.artifact_redirect(job_id, relative_path)


def create_backend(mode: str, core_url: str, core_token: str = ""):
    normalized = mode.strip().lower().replace("-", "_")
    if normalized in {"local", "studio"}:
        return LocalCoreBackend()
    if normalized in {"core_api", "magiclayercore", "remote"}:
        if not core_url:
            raise ValueError("MAGICLAYER_CORE_URL is required when STUDIO_BACKEND=core_api")
        return RemoteCoreBackend(core_url, token=core_token)
    raise ValueError(
        f"Unsupported STUDIO_BACKEND={mode!r}; expected 'local' or 'core_api'"
    )
