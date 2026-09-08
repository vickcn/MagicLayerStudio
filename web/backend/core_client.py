"""Small HTTP adapter for delegating heavy processing to MagicLayerCore."""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


class MagicLayerCoreClient:
    def __init__(self, base_url: str, token: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token
        self.timeout = timeout

    def _request(self, url: str, data=None, headers=None, method=None):
        request_headers = dict(headers or {})
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        return urlopen(Request(url, data=data, headers=request_headers, method=method), timeout=self.timeout)

    def submit_and_wait(self, input_path: Path, output_dir: Path, params: dict) -> dict:
        boundary = "----MagicLayerCoreBoundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{input_path.name}\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + input_path.read_bytes()
        body += (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"params\"\r\n\r\n"
                 + json.dumps(params) + f"\r\n--{boundary}--\r\n").encode()
        with self._request(
            urljoin(self.base_url, "v1/jobs"),
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        ) as response:
            job_id = json.load(response)["job_id"]
        while True:
            with self._request(urljoin(self.base_url, f"v1/jobs/{job_id}")) as response:
                status = json.load(response)
            if status.get("status") in ("done", "completed"):
                break
            if status.get("status") in ("error", "failed"):
                raise RuntimeError(status.get("error", "Core job failed"))
            time.sleep(1)
        output_dir.mkdir(parents=True, exist_ok=True)
        if status.get("rebuilt_pptx"):
            rel_pptx = status["rebuilt_pptx"]
            target_pptx = output_dir / rel_pptx
            target_pptx.parent.mkdir(parents=True, exist_ok=True)
            self._download(urljoin(self.base_url, f"v1/jobs/{job_id}/artifacts/{rel_pptx}"), target_pptx)
            status["rebuilt_pptx_path"] = str(target_pptx)

        for page in status.get("pages", []):
            page_dir = output_dir / page["page_id"]
            page_dir.mkdir(parents=True, exist_ok=True)
            for relative in page.get("files", []):
                target = output_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                self._download(urljoin(self.base_url, f"v1/jobs/{job_id}/artifacts/{relative}"), target)
            local_dir = output_dir / page["page_id"]
            page["output_dir"] = str(local_dir)
            page["layers_json"] = str(local_dir / "layers.json")
            page["objects_json"] = str(local_dir / "objects.json")
            page["background"] = next((str(local_dir / name) for name in ("background_telea.png", "background_ns.png", "background_sd.png") if (local_dir / name).exists()), None)
            layer_dir = local_dir / "text_layers"
            page["layer_files"] = [str(f) for f in sorted(layer_dir.glob("*.png"))] if layer_dir.exists() else []
            page["layer_count"] = len(page["layer_files"])
        return status

    def _download(self, url: str, target: Path) -> None:
        try:
            with self._request(url) as response:
                target.write_bytes(response.read())
        except Exception:
            pass
