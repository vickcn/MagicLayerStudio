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


def create_conservative_inpaint_mask(
    combined_text_mask: np.ndarray,
    kernel_size: int = 3,
    max_kernel_size: int = 7,
) -> tuple[np.ndarray, int]:
    """Make a small text-only repair mask safe for semantic backgrounds.

    Legacy requests can carry a much larger dilation value. Classical
    inpainting cannot reconstruct faces or objects behind a large text block,
    so retain only the text alpha and cap its expansion.
    """
    effective_kernel = max(1, min(int(kernel_size), max_kernel_size))
    if effective_kernel % 2 == 0:
        effective_kernel -= 1

    text_binary = (combined_text_mask >= 32).astype(np.uint8) * 255
    kernel = np.ones((effective_kernel, effective_kernel), np.uint8)
    return cv2.dilate(text_binary, kernel, iterations=1), effective_kernel


def build_block_text_mask_from_layers(
    layers: Sequence[dict],
    canvas_size: tuple[int, int],
    padding: int = 12,
    min_block_height: int = 18,
) -> np.ndarray:
    height, width = canvas_size
    mask = np.zeros((height, width), dtype=np.uint8)

    for layer in layers:
        try:
            x = int(layer["x"])
            y = int(layer["y"])
            w = int(layer["width"])
            h = int(layer["height"])
        except KeyError:
            continue

        if w <= 0 or h <= 0:
            continue

        # 很小的標點可以留給 alpha mask，避免整塊挖太大
        if h < min_block_height and w < min_block_height:
            continue

        pad_x = max(padding, round(h * 0.25))
        pad_y = max(padding, round(h * 0.35))

        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(width, x + w + pad_x)
        y2 = min(height, y + h + pad_y)

        cv2.rectangle(
            mask,
            (x1, y1),
            (x2, y2),
            255,
            thickness=-1,
        )

    return mask


def create_hybrid_inpaint_mask(
    combined_text_mask: np.ndarray,
    block_text_mask: np.ndarray,
    kernel_size: int = 15,
    iterations: int = 1,
) -> np.ndarray:
    alpha_kernel = np.ones((kernel_size, kernel_size), np.uint8)

    alpha_expanded = cv2.dilate(
        combined_text_mask,
        alpha_kernel,
        iterations=iterations,
    )

    # block 不要太硬，先 close，再 dilate
    block_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size * 2 + 1, kernel_size * 2 + 1),
    )

    block_expanded = cv2.morphologyEx(
        block_text_mask,
        cv2.MORPH_CLOSE,
        block_kernel,
    )

    block_expanded = cv2.dilate(
        block_expanded,
        block_kernel,
        iterations=1,
    )

    return np.maximum(alpha_expanded, block_expanded)


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


def evaluate_local_background_complexity(
    image: np.ndarray,
    combined_mask: np.ndarray,
    layer: dict,
) -> dict:
    """Assess whether the background around a text layer is smooth or complex/semantic."""
    h_img, w_img = image.shape[:2]
    x = max(0, int(layer.get("x", 0)))
    y = max(0, int(layer.get("y", 0)))
    w = max(1, int(layer.get("width", 1)))
    h = max(1, int(layer.get("height", 1)))

    pad = max(16, int(h * 0.25))
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(w_img, x + w + pad)
    y2 = min(h_img, y + h + pad)

    img_crop = image[y1:y2, x1:x2]
    mask_crop = combined_mask[y1:y2, x1:x2]
    bg_mask = mask_crop < 32

    if np.count_nonzero(bg_mask) < 40:
        return {
            "id": layer.get("id"),
            "text": layer.get("text", ""),
            "height": h,
            "is_complex": False,
            "blurred_lap_var": 0.0,
            "edge_density": 0.0,
            "recommended_kernel": 7,
            "inpaint_mode": "smooth_fallback",
        }

    gray_crop = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray_crop, (5, 5), 0)

    lap = cv2.Laplacian(blurred, cv2.CV_64F)
    lap_bg = lap[bg_mask]
    lap_var = float(np.var(lap_bg)) if len(lap_bg) > 0 else 0.0

    canny = cv2.Canny(blurred, 30, 90)
    canny_bg = canny[bg_mask]
    edge_density = float(np.count_nonzero(canny_bg > 0) / np.count_nonzero(bg_mask)) if len(canny_bg) > 0 else 0.0

    # Decision rule: High edge density (>5.5%) or high structure -> complex/portrait background
    is_complex = (edge_density >= 0.055) or (lap_var >= 60.0 and edge_density >= 0.045)

    if is_complex:
        k_size = max(3, min(5, int(h * 0.02)))
        if k_size % 2 == 0:
            k_size -= 1
        mode = "conservative_complex"
    else:
        style_hint = layer.get("style_hint", {})
        has_stroke_or_shadow = bool(style_hint.get("stroke_color_rgb") or style_hint.get("likely_bold"))
        ratio = 0.07 if has_stroke_or_shadow else 0.05
        k_size = max(7, min(29, int(h * ratio)))
        if k_size % 2 == 0:
            k_size += 1
        mode = "adaptive_smooth"

    return {
        "id": layer.get("id"),
        "text": layer.get("text", ""),
        "height": h,
        "is_complex": is_complex,
        "blurred_lap_var": round(lap_var, 2),
        "edge_density": round(edge_density, 4),
        "recommended_kernel": k_size,
        "inpaint_mode": mode,
    }


def create_adaptive_inpaint_mask(
    image: np.ndarray,
    combined_text_mask: np.ndarray,
    layers: Sequence[dict],
    fallback_kernel_size: int = 3,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Build an inpaint mask adaptively based on local background complexity and font scale."""
    h_img, w_img = image.shape[:2]
    if not layers:
        mask, effective_k = create_conservative_inpaint_mask(combined_text_mask, fallback_kernel_size)
        return mask, np.zeros_like(mask), []

    inpaint_mask = np.zeros((h_img, w_img), dtype=np.uint8)
    smooth_regions_mask = np.zeros((h_img, w_img), dtype=np.uint8)
    layer_reports = []

    for layer in layers:
        info = evaluate_local_background_complexity(image, combined_text_mask, layer)
        layer_reports.append(info)

        x = max(0, int(layer.get("x", 0)))
        y = max(0, int(layer.get("y", 0)))
        w = max(1, int(layer.get("width", 1)))
        h = max(1, int(layer.get("height", 1)))

        layer_mask = combined_text_mask[y:y+h, x:x+w]
        k_size = info["recommended_kernel"]
        kernel = np.ones((k_size, k_size), np.uint8)

        dilated = cv2.dilate((layer_mask >= 32).astype(np.uint8) * 255, kernel, iterations=1)
        inpaint_mask[y:y+h, x:x+w] = np.maximum(inpaint_mask[y:y+h, x:x+w], dilated)

        if not info["is_complex"]:
            smooth_regions_mask[y:y+h, x:x+w] = np.maximum(smooth_regions_mask[y:y+h, x:x+w], dilated)

    return inpaint_mask, smooth_regions_mask, layer_reports


def run_classical_inpainting_baseline(
    image_path: Path,
    output_dir: Path,
    layers: Sequence[dict],
    dilate_kernel_size: int = 3,
    inpaint_radius: int = 1,
    adaptive: bool = True,
) -> dict:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read image: {image_path}")

    combined_text_mask = load_or_build_combined_text_mask(
        image,
        output_dir,
        layers,
    )
    
    if adaptive:
        inpaint_mask, smooth_mask, layer_reports = create_adaptive_inpaint_mask(
            image,
            combined_text_mask,
            layers,
            fallback_kernel_size=dilate_kernel_size,
        )
        effective_radius = max(inpaint_radius, 3) if np.any(smooth_mask > 0) else inpaint_radius
        effective_mode = "adaptive_texture_aware"
    else:
        inpaint_mask, effective_dilate_kernel_size = create_conservative_inpaint_mask(
            combined_text_mask,
            kernel_size=dilate_kernel_size,
        )
        smooth_mask = np.zeros_like(inpaint_mask)
        layer_reports = []
        effective_radius = inpaint_radius
        effective_mode = "fixed_conservative"

    telea = cv2.inpaint(
        image,
        inpaint_mask,
        effective_radius,
        cv2.INPAINT_TELEA,
    )

    ns = cv2.inpaint(
        image,
        inpaint_mask,
        effective_radius,
        cv2.INPAINT_NS,
    )

    # Post-smoothing feathering on smooth regions only to eliminate streak artifacts
    if adaptive and np.any(smooth_mask > 0):
        blurred_telea = cv2.bilateralFilter(telea, d=9, sigmaColor=30, sigmaSpace=30)
        feather = cv2.GaussianBlur(smooth_mask.astype(np.float32) / 255.0, (7, 7), 0)[:, :, None]
        telea = (telea.astype(np.float32) * (1.0 - feather) + blurred_telea.astype(np.float32) * feather).astype(np.uint8)

        blurred_ns = cv2.bilateralFilter(ns, d=9, sigmaColor=30, sigmaSpace=30)
        ns = (ns.astype(np.float32) * (1.0 - feather) + blurred_ns.astype(np.float32) * feather).astype(np.uint8)

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
            "mode": "adaptive_texture_aware",
            "requested_dilate_kernel_size": dilate_kernel_size,
            "inpaint_radius": effective_radius,
            "layer_evaluations": layer_reports,
        },
        "inpainting": {
            "radius": effective_radius,
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
