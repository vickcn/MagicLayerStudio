"""Small HTTP adapter for delegating heavy processing to MagicLayerCore."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urljoin
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

    def _json_request(self, path: str, payload=None, method="POST") -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"} if data is not None else {}
        with self._request(urljoin(self.base_url, path), data=data, headers=headers, method=method) as response:
            return json.load(response)

    def prepare_upload(self, filename: str, content_type: str, size: Optional[int]) -> dict:
        return self._json_request(
            "v1/uploads/prepare",
            {"filename": filename, "content_type": content_type, "size": size},
        )

    def complete_upload(self, upload_id: str, options: dict, filename: Optional[str] = None, size: Optional[int] = None) -> dict:
        return self._json_request(
            f"v1/uploads/{quote(upload_id, safe='')}/complete",
            {"options": options, "filename": filename, "size": size},
        )

    def get_job(self, job_id: str) -> dict:
        return self._json_request(f"v1/jobs/{quote(job_id, safe='')}", method="GET")

    def health(self) -> dict:
        return self._json_request("health", method="GET")

    def delete_job(self, job_id: str) -> dict:
        return self._json_request(f"v1/jobs/{quote(job_id, safe='')}", method="DELETE")

    def result(self, job_id: str) -> dict:
        status = self.get_job(job_id)
        pages = []
        for page in status.get("pages", []):
            page_id = page.get("page_id", "")
            files = page.get("files", [])
            page_data = dict(page)

            def artifact_url(relative: Optional[str]) -> Optional[str]:
                if not relative:
                    return None
                return urljoin(
                    self.base_url,
                    f"v1/jobs/{quote(job_id, safe='')}/artifacts/{quote(relative, safe='/')}",
                )

            page_data["source_image"] = artifact_url(page.get("source_image"))
            page_data["background"] = artifact_url(page.get("background"))
            page_data["layers_json"] = artifact_url(page.get("layers_json"))
            page_data["objects_json"] = artifact_url(page.get("objects_json"))
            page_data["layer_files"] = [artifact_url(path) for path in page.get("layer_files", [])]
            page_data["output_dir"] = None
            page_data["layer_count"] = len(page_data["layer_files"])
            pages.append(page_data)

        rebuilt_pptx = artifact_url_for(self.base_url, job_id, status.get("rebuilt_pptx"))
        return {
            "job_id": job_id,
            "pages": pages,
            "rebuilt_pptx": rebuilt_pptx,
            "size_mb": None,
        }

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


def artifact_url_for(base_url: str, job_id: str, relative: Optional[str]) -> Optional[str]:
    if not relative:
        return None
    return urljoin(
        base_url,
        f"v1/jobs/{quote(job_id, safe='')}/artifacts/{quote(relative, safe='/')}",
    )
