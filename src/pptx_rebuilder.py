from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Union


DEFAULT_SLIDE_WIDTH_IN = 13.333333
EMU_PER_INCH = 914400


def rebuild_pptx_from_document(
    document_json_path: Path,
    output_pptx_path: Path,
) -> Path:
    try:
        import pptx  # noqa: F401
    except ImportError:
        return rebuild_pptx_with_padocr(document_json_path, output_pptx_path)

    return _rebuild_pptx(document_json_path, output_pptx_path)


def rebuild_pptx_with_padocr(
    document_json_path: Path,
    output_pptx_path: Path,
) -> Path:
    conda_exe = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if conda_exe is None:
        raise RuntimeError(
            "python-pptx is not available. Activate padocr or make conda available."
        )

    subprocess.run(
        [
            conda_exe,
            "run",
            "--no-capture-output",
            "-n",
            "padocr",
            "python",
            "-m",
            "src.pptx_rebuilder",
            str(document_json_path),
            str(output_pptx_path),
        ],
        check=True,
    )
    return output_pptx_path


def _resolve_file_path(base_dir: Path, path_val: str | Path) -> Path:
    p = Path(str(path_val))
    if p.is_absolute() and p.exists():
        return p
    if p.exists():
        return p.resolve()
    if (base_dir / p).exists():
        return (base_dir / p).resolve()
    if (base_dir / p.name).exists():
        return (base_dir / p.name).resolve()
    return base_dir / p


def _rebuild_pptx(document_json_path: Path, output_pptx_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Emu

    document_json_path = document_json_path.resolve()
    output_pptx_path = output_pptx_path.resolve()
    output_dir = document_json_path.parent

    with open(document_json_path, "r", encoding="utf-8") as file:
        document = json.load(file)

    pages = document.get("pages", [])
    if not pages:
        raise RuntimeError(f"No pages found in: {document_json_path}")

    first_objects = _load_objects_json(output_dir, pages[0])
    canvas_width = int(first_objects["canvas"]["width"])
    canvas_height = int(first_objects["canvas"]["height"])
    slide_width = int(round(DEFAULT_SLIDE_WIDTH_IN * EMU_PER_INCH))
    slide_height = int(round(slide_width * canvas_height / canvas_width))

    prs = Presentation()
    prs.slide_width = Emu(slide_width)
    prs.slide_height = Emu(slide_height)
    blank_layout = prs.slide_layouts[6]

    for page in pages:
        objects_json = _load_objects_json(output_dir, page)
        page_dir_val = page.get("output_dir") or page.get("output", "")
        page_dir = _resolve_file_path(output_dir, page_dir_val)
        page_canvas_width = int(objects_json["canvas"]["width"])
        page_canvas_height = int(objects_json["canvas"]["height"])

        slide = prs.slides.add_slide(blank_layout)
        background_path = _resolve_background_path(output_dir, page)
        slide.shapes.add_picture(
            str(background_path),
            0,
            0,
            width=prs.slide_width,
            height=prs.slide_height,
        )

        for obj in objects_json.get("objects", []):
            image_path = _resolve_file_path(page_dir, obj.get("file", ""))
            if not image_path.exists():
                if "image_path" in obj:
                    image_path = _resolve_file_path(page_dir, obj["image_path"])
                if not image_path.exists():
                    continue

            left = _scale_emu(int(obj["x"]), page_canvas_width, prs.slide_width)
            top = _scale_emu(int(obj["y"]), page_canvas_height, prs.slide_height)
            width = _scale_emu(int(obj["width"]), page_canvas_width, prs.slide_width)
            height = _scale_emu(int(obj["height"]), page_canvas_height, prs.slide_height)
            slide.shapes.add_picture(
                str(image_path),
                left,
                top,
                width=width,
                height=height,
            )

    output_pptx_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_pptx_path))
    return output_pptx_path


def _load_objects_json(output_dir: Path, page: dict) -> dict:
    objects_path_val = page.get("objects_json", "")
    objects_path = _resolve_file_path(output_dir, objects_path_val)
    with open(objects_path, "r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_background_path(output_dir: Path, page: dict) -> Path:
    background = page.get("background") or page.get("background_path")
    if background:
        background_path = _resolve_file_path(output_dir, background)
        if background_path.exists():
            return background_path

    page_obj = page.get("page")
    source_image = (
        page.get("source_image")
        or (page_obj.get("image_path") if isinstance(page_obj, dict) else None)
    )
    if not source_image:
        raise RuntimeError(f"Page has no background or source image: {page}")

    source_path = _resolve_file_path(output_dir, source_image)
    if source_path.exists():
        return source_path

    raise RuntimeError(f"Cannot resolve page background: {source_image}")


def _scale_emu(value: int, source_size: int, target_size: int):
    from pptx.util import Emu

    return Emu(int(round(value / source_size * int(target_size))))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("document_json", type=Path)
    parser.add_argument("output_pptx", type=Path)
    args = parser.parse_args(argv)
    rebuilt_path = rebuild_pptx_from_document(args.document_json, args.output_pptx)
    print(rebuilt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
