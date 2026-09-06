from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image

try:
    from src.inpainting.background_harmonizer import BackgroundHarmonizer
    from src.inpainting.classical_inpainting import run_classical_inpainting_baseline
    from src.inpainting.roi_rebuilder import build_object_roi, crop_roi
    from src.inpainting.sd_inpainter import SDInpainter
except ModuleNotFoundError:
    from inpainting.background_harmonizer import BackgroundHarmonizer
    from inpainting.classical_inpainting import run_classical_inpainting_baseline
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
    harmonize: bool = True,
    harmonizer: BackgroundHarmonizer | None = None,
) -> Path | None:

    if backend == "none":
        return None

    if backend in ("telea", "ns"):
        run_classical_inpainting_baseline(
            image_path,
            output_dir,
            layers,
            dilate_kernel_size=dilate_kernel_size,
            inpaint_radius=inpaint_radius,
        )

        bg_path = output_dir / f"background_{backend}.png"
        if not bg_path.exists() and backend == "telea":
            bg_path = output_dir / "background_telea.png"

        if harmonize:
            mask_path = output_dir / "inpaint_mask.png"
            if not mask_path.exists():
                mask_path = output_dir / "combined_text_mask.png"

            if mask_path.exists():
                mask = Image.open(mask_path).convert("L")

                if harmonizer is None:
                    harmonizer = BackgroundHarmonizer(
                        feather_radius=12,
                        transition_width=24,
                    )

                for candidate_name in ("background_telea.png", "background_ns.png"):
                    candidate_path = output_dir / candidate_name
                    if candidate_path.exists():
                        repaired = Image.open(candidate_path).convert("RGB")
                        if mask.size != repaired.size:
                            mask = mask.resize(repaired.size, Image.NEAREST)
                        # 不要拿含字的 original 原圖作為 feather reference，以避免字跡滲漏混回邊緣
                        reference = repaired.copy()
                        harmonized = harmonizer.harmonize(reference, repaired, mask)
                        harmonized.save(candidate_path)

        return bg_path

    if backend == "sd":
        return _run_sd(
            image_path=image_path,
            output_dir=output_dir,
            layers=layers,
            objects=objects,
            dilate_kernel_size=dilate_kernel_size,
            inpaint_radius=inpaint_radius,
            harmonize=harmonize,
            harmonizer=harmonizer,
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


def _build_layer_mask(
    image_size: tuple[int, int],
    output_dir: Path,
    layer: dict,
) -> Image.Image:

    mask = Image.new(
        "L",
        image_size,
        0,
    )

    layer_file = layer.get("file")

    if not layer_file:
        return mask

    layer_path = output_dir / layer_file

    if not layer_path.exists():
        return mask

    rgba = Image.open(layer_path).convert("RGBA")
    alpha = rgba.getchannel("A")

    mask.paste(
        alpha,
        (
            int(layer["x"]),
            int(layer["y"]),
        ),
        alpha,
    )

    return mask


def _run_sd(
    image_path: Path,
    output_dir: Path,
    layers: Sequence[dict],
    objects: Sequence[dict],
    dilate_kernel_size: int = 15,
    inpaint_radius: int = 5,
    harmonize: bool = True,
    harmonizer: BackgroundHarmonizer | None = None,
) -> Path:

    # 先用 Telea 將整頁文字擦除挖掉，取得乾淨的底圖作為 SD 擴散延伸的基準
    run_classical_inpainting_baseline(
        image_path,
        output_dir,
        layers,
        dilate_kernel_size=dilate_kernel_size,
        inpaint_radius=inpaint_radius,
    )

    telea_bg_path = output_dir / "background_telea.png"
    if telea_bg_path.exists():
        working = Image.open(telea_bg_path).convert("RGB")
    else:
        working = Image.open(image_path).convert("RGB")

    page_mask = _build_page_mask(
        image_size=working.size,
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

    for index, layer in enumerate(layers):

        width = int(layer["width"])
        height = int(layer["height"])

        if width < 20 or height < 20:
            continue

        expand_radius = max(
            12,
            min(
                40,
                round(height * 0.15),
            ),
        )

        layer_mask = _build_layer_mask(
            image_size=working.size,
            output_dir=output_dir,
            layer=layer,
        )

        if layer_mask.getbbox() is None:
            continue

        roi = build_object_roi(
            obj={
                "x": int(layer["x"]),
                "y": int(layer["y"]),
                "width": width,
                "height": height,
            },
            image_size=working.size,
            min_padding=max(
                128,
                round(height * 0.8),
            ),
            max_padding=384,
        )

        roi_image, roi_mask = crop_roi(
            image=working,
            mask=layer_mask,
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
                "Seamlessly reconstruct the masked area as the same "
                "scene and background. Use the unmasked surroundings as "
                "visual reference. Continue existing shapes, patterns, "
                "gradients, lighting, perspective, texture, colors and "
                "composition through the masked area."
            ),
            negative_prompt=(
                "text, letters, words, typography, writing, "
                "logo, watermark, sign"
            ),
            guidance_scale=4.5,
            steps=30,
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

    if harmonize:
        # 使用 expanded hybrid mask 替代單純 raw alpha page_mask
        mask_path = output_dir / "inpaint_mask.png"
        if mask_path.exists():
            final_mask = Image.open(mask_path).convert("L")
        else:
            final_mask = page_mask

        # 使用 Telea 或已抹平底圖做 reference，防止原始文字滲漏
        if telea_bg_path.exists():
            reference = Image.open(telea_bg_path).convert("RGB")
        else:
            reference = working.copy()

        if harmonizer is None:
            harmonizer = BackgroundHarmonizer(
                feather_radius=12,
                transition_width=24,
            )
        working = harmonizer.harmonize(reference, working, final_mask)

    output_path = (
        output_dir
        / "background_sd.png"
    )

    working.save(output_path)

    return output_path
