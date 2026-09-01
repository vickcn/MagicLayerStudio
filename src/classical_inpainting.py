import json
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


def build_combined_text_mask_from_layers(
    output_dir: Path,
    layers: Sequence[dict],
    canvas_size: tuple[int, int],
) -> np.ndarray:
    height, width = canvas_size
    combined_mask = np.zeros((height, width), dtype=np.uint8)

    for layer in layers:
        rgba = cv2.imread(
            str(output_dir / str(layer["file"])),
            cv2.IMREAD_UNCHANGED,
        )
        if rgba is None or rgba.ndim != 3 or rgba.shape[2] < 4:
            continue

        alpha = rgba[:, :, 3]
        x = int(layer["x"])
        y = int(layer["y"])
        x2 = min(width, x + alpha.shape[1])
        y2 = min(height, y + alpha.shape[0])

        if x2 <= x or y2 <= y:
            continue

        region = combined_mask[y:y2, x:x2]
        np.maximum(
            region,
            alpha[: y2 - y, : x2 - x],
            out=region,
        )

    return combined_mask


def load_or_build_combined_text_mask(
    image: np.ndarray,
    output_dir: Path,
    layers: Sequence[dict],
) -> np.ndarray:
    mask_path = output_dir / "combined_text_mask.png"
    if mask_path.exists():
        combined_mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if combined_mask is not None:
            return combined_mask

    return build_combined_text_mask_from_layers(
        output_dir,
        layers,
        image.shape[:2],
    )


def create_inpaint_mask(
    combined_text_mask: np.ndarray,
    kernel_size: int = 5,
    iterations: int = 1,
) -> np.ndarray:
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    return cv2.dilate(
        combined_text_mask,
        kernel,
        iterations=iterations,
    )


def create_source_with_mask_preview(
    image: np.ndarray,
    mask: np.ndarray,
    alpha: float = 0.35,
) -> np.ndarray:
    preview = image.copy()
    overlay = np.zeros_like(image)
    overlay[:, :] = (0, 0, 255)

    mask_3c = (mask > 0)[:, :, None].astype(np.float32)
    blended = (
        image.astype(np.float32) * (1.0 - alpha * mask_3c)
        + overlay.astype(np.float32) * (alpha * mask_3c)
    )
    preview[:, :] = np.clip(blended, 0, 255).astype(np.uint8)
    return preview


# def run_classical_inpainting_baseline(
#     image_path: Path,
#     output_dir: Path,
#     layers: Sequence[dict],
#     radius: int = 5,
# ) -> dict:
def run_classical_inpainting_baseline(
    image_path: Path,
    output_dir: Path,
    layers: Sequence[dict],
    dilate_kernel_size: int = 5,
    inpaint_radius: int = 5,
) -> dict:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    combined_text_mask = load_or_build_combined_text_mask(
        image,
        output_dir,
        layers,
    )
    inpaint_mask = create_inpaint_mask(
        combined_text_mask,
        kernel_size=dilate_kernel_size,
    )

    # telea = cv2.inpaint(
    #     image,
    #     inpaint_mask,
    #     radius,
    #     cv2.INPAINT_TELEA,
    # )
    # ns = cv2.inpaint(
    #     image,
    #     inpaint_mask,
    #     radius,
    #     cv2.INPAINT_NS,
    # )
    telea = cv2.inpaint(
        image,
        inpaint_mask,
        inpaint_radius,
        cv2.INPAINT_TELEA,
    )

    ns = cv2.inpaint(
        image,
        inpaint_mask,
        inpaint_radius,
        cv2.INPAINT_NS,
    )

    preview = create_source_with_mask_preview(image, inpaint_mask)

    telea_path = output_dir / "background_telea.png"
    ns_path = output_dir / "background_ns.png"
    inpaint_mask_path = output_dir / "inpaint_mask.png"
    preview_path = output_dir / "source_with_mask_preview.png"
    metrics_path = output_dir / "metrics.json"

    cv2.imwrite(str(telea_path), telea)
    cv2.imwrite(str(ns_path), ns)
    cv2.imwrite(str(inpaint_mask_path), inpaint_mask)
    cv2.imwrite(str(preview_path), preview)

    mask_binary = inpaint_mask > 0
    source_mask_binary = combined_text_mask > 0

    if np.any(mask_binary):
        telea_masked_diff = np.mean(
            np.abs(
                telea.astype(np.float32)[mask_binary]
                - image.astype(np.float32)[mask_binary]
            )
        )
        ns_masked_diff = np.mean(
            np.abs(
                ns.astype(np.float32)[mask_binary]
                - image.astype(np.float32)[mask_binary]
            )
        )
        methods_masked_diff = np.mean(
            np.abs(
                telea.astype(np.float32)[mask_binary]
                - ns.astype(np.float32)[mask_binary]
            )
        )
    else:
        telea_masked_diff = 0.0
        ns_masked_diff = 0.0
        methods_masked_diff = 0.0

    metrics = {
        "source_image": str(image_path),
        "image_size": {
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
        },
        "mask": {
            "source_mask_pixels": int(np.count_nonzero(source_mask_binary)),
            "source_mask_ratio": float(np.count_nonzero(source_mask_binary) / source_mask_binary.size),
            "inpaint_mask_pixels": int(np.count_nonzero(mask_binary)),
            "inpaint_mask_ratio": float(np.count_nonzero(mask_binary) / mask_binary.size),
            # "dilate_kernel_size": 5,
            "dilate_kernel_size": dilate_kernel_size,
            "dilate_iterations": 1,
        },
        "inpainting": {
            # "radius": radius,
            "radius": inpaint_radius,
            "methods": [
                "cv2.INPAINT_TELEA",
                "cv2.INPAINT_NS",
            ],
            "telea_masked_mean_abs_diff": float(telea_masked_diff),
            "ns_masked_mean_abs_diff": float(ns_masked_diff),
            "telea_vs_ns_masked_mean_abs_diff": float(methods_masked_diff),
        },
        "outputs": {
            "background_telea": str(telea_path.relative_to(output_dir)),
            "background_ns": str(ns_path.relative_to(output_dir)),
            "inpaint_mask": str(inpaint_mask_path.relative_to(output_dir)),
            "source_with_mask_preview": str(preview_path.relative_to(output_dir)),
        },
    }

    with open(metrics_path, "w", encoding="utf-8") as file:
        json.dump(metrics, file, ensure_ascii=False, indent=2)

    return metrics
