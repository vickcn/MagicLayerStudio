"""Remote result data retains relative artifact paths for the Studio BFF."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_test() -> None:
    from web.backend.core_client import MagicLayerCoreClient

    client = MagicLayerCoreClient("https://core.example.invalid", token="not-a-secret")
    client.get_job = lambda _job_id: {
        "job_id": "job-1",
        "pages": [{
            "page_id": "page-1",
            "source_image": "page-1/source.png",
            "background": "page-1/background.png",
            "layers_json": "page-1/layers.json",
            "objects_json": "page-1/objects.json",
            "layer_files": ["page-1/text_layers/title.png"],
        }],
        "rebuilt_pptx": "rebuilt.pptx",
    }

    result = client.result("job-1")
    page = result["pages"][0]
    assert page["source_image"] == "page-1/source.png"
    assert page["layer_files"] == ["page-1/text_layers/title.png"]
    assert result["rebuilt_pptx"] == "rebuilt.pptx"


if __name__ == "__main__":
    run_test()
