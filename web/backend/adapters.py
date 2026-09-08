"""Backend adapters used by MagicLayerStudio.

The Studio contract stays the same while the implementation can be switched
between the local pipeline and MagicLayerCore's HTTP API by configuration.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


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
