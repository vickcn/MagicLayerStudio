"""Studio exposes actionable, non-sensitive Core failures to the browser."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.error import HTTPError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_test() -> None:
    from web.backend.app import _core_http_error
    from web.backend.core_client import CoreRequestError

    unavailable = _core_http_error(CoreRequestError(503, "job_state_unavailable"), "complete_upload")
    assert unavailable.status_code == 503
    assert unavailable.detail == {
        "code": "core_job_state_unavailable",
        "message": "Core 暫時無法建立工作狀態，請稍後重試。",
        "retryable": True,
    }

    missing = _core_http_error(HTTPError("https://example.invalid", 404, "not found", {}, None), "complete_upload")
    assert missing.status_code == 404
    assert missing.detail["code"] == "upload_not_found"
    assert missing.detail["retryable"] is False


if __name__ == "__main__":
    run_test()
