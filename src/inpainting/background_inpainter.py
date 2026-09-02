from __future__ import annotations

import statistics
from pathlib import Path
from typing import Sequence

from PIL import Image

try:
    from src.classical_inpainting import run_classical_inpainting_baseline
    from src.inpainting.roi_rebuilder import build_object_roi, crop_roi
    from src.inpainting.sd_inpainter import SDInpainter
except ModuleNotFoundError:
    from classical_inpainting import run_classical_inpainting_baseline
    from inpainting.roi_rebuilder import build_object_roi, crop_roi
    from inpainting.sd_inpainter import SDInpainter


def inpaint_background(
    image_path: Path,
    output_dir: Path,
    layers: Sequence[dict],
    objects: Sequence[dict],
    backend: str = "telea",
    dilate_kernel_size: int = 15,
    inpaint_radius: int = 5,
) -> Path | None:

    if backend == "none":
        return None

    if backend == "telea":
        run_classical_inpainting_baseline(
            image_path,
            output_dir,
            layers,
            dilate_kernel_size=dilate_kernel_size,
            inpaint_radius=inpaint_radius,
        )

        return output_dir / "background_telea.png"

    if backend == "sd":
        return _run_sd(
            image_path=image_path,
            output_dir=output_dir,
            layers=layers,
            objects=objects,
        )

    raise ValueError(
        f"Unsupported inpaint backend: {backend}"
    )


def _build_page_mask(
    image_size: tuple[int, int],
    output_dir: Path,
    layers: Sequence[dict],
) -> Image.Image:

    mask = Image.new(
        "L",
        image_size,
        0,
    )

    for layer in layers:
        layer_file = layer.get("file")

        if not layer_file:
            continue

        layer_path = output_dir / layer_file

        if not layer_path.exists():
            continue

        rgba = Image.open(layer_path).convert("RGBA")
        alpha = rgba.getchannel("A")

        x = int(layer["x"])
        y = int(layer["y"])

        mask.paste(
            alpha,
            (x, y),
            alpha,
        )

    return mask


def _get_object_text_height(
    obj: dict,
    layers: Sequence[dict],
) -> int:

    layer_ids = set(obj["layer_ids"])

    heights = [
        int(layer["height"])
        for layer in layers
        if layer["id"] in layer_ids
    ]

    if not heights:
        return int(obj["height"])

    return round(statistics.median(heights))


def _run_sd(
    image_path: Path,
    output_dir: Path,
    layers: Sequence[dict],
    objects: Sequence[dict],
) -> Path:

    image = Image.open(
        image_path
    ).convert("RGB")

    working = image.copy()

    page_mask = _build_page_mask(
        image_size=image.size,
        output_dir=output_dir,
        layers=layers,
    )

    debug_dir = (
        output_dir / "sd_rois"
    )

    debug_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    page_mask.save(
        debug_dir / "page_mask.png"
    )

    inpainter = SDInpainter()

    for index, obj in enumerate(objects):

        width = int(obj["width"])
        height = int(obj["height"])

        if width < 20 or height < 20:
            continue

        text_height = _get_object_text_height(
            obj=obj,
            layers=layers,
        )

        expand_radius = max(
            12,
            min(
                40,
                round(text_height * 0.15),
            ),
        )

        roi = build_object_roi(
            obj=obj,
            image_size=image.size,
        )

        roi_image, roi_mask = crop_roi(
            image=working,
            mask=page_mask,
            roi=roi,
        )

        if roi_mask.getbbox() is None:
            continue

        roi_image.save(
            debug_dir
            / f"roi_{index:03d}.png"
        )

        roi_mask.save(
            debug_dir
            / f"mask_{index:03d}.png"
        )

        repaired = inpainter.inpaint(
            image=roi_image,
            mask=roi_mask,
            prompt=(
                "continue only the existing surrounding "
                "background naturally, preserve the original "
                "background structure, lighting, texture, "
                "colors and composition, seamless background, "
                "empty background"
            ),
            negative_prompt=(
                "text, letters, words, typography, writing, "
                "poster, advertisement, banner, billboard, "
                "logo, watermark, sign, symbol, "
                "human, person, face, object, "
                "frame, panel, chart, interface, "
                "illustration, collage"
            ),
            guidance_scale=3.0,
            steps=25,
            mask_expand_radius=expand_radius,
        )

        repaired.save(
            debug_dir
            / f"repaired_{index:03d}.png"
        )

        working.paste(
            repaired,
            (roi.x1, roi.y1),
        )

    output_path = (
        output_dir
        / "background_sd.png"
    )

    working.save(output_path)

    return output_path
