import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

try:
    from src.text_style_estimator import estimate_style_from_rgba
except ImportError:
    from text_style_estimator import estimate_style_from_rgba


@dataclass(frozen=True)
class ExtractionOptions:
    image_path: Path
    json_path: Path
    output_dir: Path
    min_score: float = 0.50
    padding: int = 8
    debug_outputs: bool = True
    extract_style_hints: bool = True  # 是否推算並記錄文字樣式提示


def create_debug_canvases(
    image: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, w = image.shape[:2]

    combined_mask = np.zeros((h, w), dtype=np.uint8)

    # 棋盤格 preview
    tile = 24
    checker = np.zeros((h, w, 3), dtype=np.uint8)

    for y in range(0, h, tile):
        for x in range(0, w, tile):
            value = 220 if ((x // tile) + (y // tile)) % 2 == 0 else 180
            checker[y : y + tile, x : x + tile] = value

    preview = checker.copy()

    # 純透明文字重建時用黑底觀看
    reconstructed = np.zeros((h, w, 3), dtype=np.uint8)

    return combined_mask, preview, reconstructed


def estimate_text_mask(crop: np.ndarray) -> np.ndarray:
    if crop.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    h, w = crop.shape[:2]
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.float32)
    border_size = max(1, min(h, w) // 12)

    borders = np.concatenate(
        [
            lab[:border_size, :, :].reshape(-1, 3),
            lab[-border_size:, :, :].reshape(-1, 3),
            lab[:, :border_size, :].reshape(-1, 3),
            lab[:, -border_size:, :].reshape(-1, 3),
        ],
        axis=0,
    )

    bg_color = np.median(borders, axis=0)
    diff = np.linalg.norm(lab - bg_color, axis=2)
    border_diff = np.linalg.norm(borders - bg_color, axis=1)
    noise_level = np.percentile(border_diff, 90)
    threshold = max(18.0, noise_level + 8.0)
    mask = (diff > threshold).astype(np.uint8) * 255

    foreground_ratio = np.count_nonzero(mask) / mask.size
    if foreground_ratio > 0.75:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, mask_a = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        _, mask_b = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        ratio_a = np.count_nonzero(mask_a) / mask_a.size
        ratio_b = np.count_nonzero(mask_b) / mask_b.size
        target_ratio = 0.25
        mask = mask_a if abs(ratio_a - target_ratio) < abs(ratio_b - target_ratio) else mask_b

    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return cv2.GaussianBlur(mask, (3, 3), 0)


def estimate_ocr_constrained_text_mask(
    crop: np.ndarray,
    polygon: np.ndarray,
) -> np.ndarray:
    """Extract bright, outlined text only inside a trusted OCR polygon.

    This is a fallback for backgrounds whose border colours vary too much for
    ``estimate_text_mask`` to infer one representative background colour.
    """
    if crop.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    polygon_mask = build_polygon_mask(crop.shape[:2], polygon)
    if not np.any(polygon_mask):
        return np.zeros(crop.shape[:2], dtype=np.uint8)

    polygon_mask = cv2.dilate(
        polygon_mask,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    bright_text = (
        (hsv[:, :, 1] <= 105)
        & (hsv[:, :, 2] >= 145)
        & (polygon_mask > 0)
    ).astype(np.uint8)
    bright_text = cv2.morphologyEx(
        bright_text,
        cv2.MORPH_OPEN,
        np.ones((2, 2), np.uint8),
    )
    bright_text = cv2.morphologyEx(
        bright_text,
        cv2.MORPH_CLOSE,
        np.ones((2, 2), np.uint8),
    )

    outline_neighborhood = cv2.dilate(
        bright_text,
        np.ones((5, 5), np.uint8),
        iterations=1,
    )
    dark_outline = (
        (gray <= 105)
        & (hsv[:, :, 1] <= 115)
        & (outline_neighborhood > 0)
        & (polygon_mask > 0)
    ).astype(np.uint8)

    return cv2.GaussianBlur(
        np.maximum(bright_text, dark_outline) * 255,
        (3, 3),
        0,
    )


def mask_has_expected_coverage(
    mask: np.ndarray,
    polygon: np.ndarray,
) -> bool:
    if mask.size == 0:
        return False

    points = np.asarray(polygon, dtype=np.float32).reshape(-1, 2)
    polygon_area = max(1.0, float(cv2.contourArea(points)))
    minimum_pixels = max(20, round(polygon_area * 0.06))
    return int(np.count_nonzero(mask >= 32)) >= minimum_pixels


def build_polygon_mask(
    shape: tuple[int, int],
    poly: np.ndarray,
) -> np.ndarray:
    polygon_mask = np.zeros(shape, dtype=np.uint8)

    if poly is None:
        return polygon_mask

    points = np.asarray(poly, dtype=np.float32).reshape(-1, 2)
    if points.shape[0] < 3:
        return polygon_mask

    cv2.fillPoly(
        polygon_mask,
        [np.round(points).astype(np.int32)],
        255,
    )

    return polygon_mask


def estimate_text_band(
    mask: np.ndarray,
    polygon_mask: np.ndarray,
) -> tuple[int, int]:
    masked = np.where(polygon_mask > 0, mask, 0)
    row_strength = np.count_nonzero(masked >= 32, axis=1)

    if row_strength.max() == 0:
        return 0, mask.shape[0] - 1

    threshold = max(4, int(round(row_strength.max() * 0.18)))
    active_rows = np.flatnonzero(row_strength >= threshold)
    if active_rows.size == 0:
        return 0, mask.shape[0] - 1

    return int(active_rows[0]), int(active_rows[-1])


def suppress_edge_spikes(
    mask: np.ndarray,
    band_top: int,
    band_bottom: int,
) -> np.ndarray:
    refined = mask.copy()
    binary = (refined >= 32).astype(np.uint8)

    band_height = max(1, band_bottom - band_top + 1)
    edge_margin = max(12, int(round(mask.shape[1] * 0.04)))
    max_strip_width = max(16, int(round(mask.shape[1] * 0.06)))
    min_span = max(12, int(round(band_height * 1.18)))

    def trim_side(columns: range) -> None:
        run = []

        for x in columns:
            ys = np.flatnonzero(binary[:, x] > 0)
            if ys.size == 0:
                if run:
                    break
                continue

            span = int(ys[-1] - ys[0] + 1)
            in_band = np.count_nonzero((ys >= band_top) & (ys <= band_bottom))
            out_of_band = ys.size - in_band

            if span >= min_span and out_of_band > in_band * 0.35:
                run.append(x)
                if len(run) > max_strip_width:
                    run.clear()
                    break
                continue

            if run:
                break

        if run:
            refined[:, run] = 0
            binary[:, run] = 0

    trim_side(range(0, min(edge_margin, mask.shape[1])))
    trim_side(range(mask.shape[1] - 1, max(mask.shape[1] - edge_margin - 1, -1), -1))
    return refined


def refine_text_mask(
    mask: np.ndarray,
    poly: np.ndarray,
) -> np.ndarray:
    if mask.size == 0 or not np.any(mask):
        return mask

    if poly is None:
        return mask

    points = np.asarray(poly, dtype=np.float32).reshape(-1, 2)
    if points.shape[0] < 3:
        return mask

    polygon_mask = build_polygon_mask(mask.shape[:2], points)
    if not np.any(polygon_mask):
        return mask

    band_top, band_bottom = estimate_text_band(mask, polygon_mask)
    mask = suppress_edge_spikes(mask, band_top, band_bottom)

    x, y, w, h = cv2.boundingRect(np.round(points).astype(np.int32))
    text_w = max(1, w)
    text_h = max(1, h)
    band_height = max(1, band_bottom - band_top + 1)

    horizontal_pad = max(2, int(round(text_w * 0.08)))
    vertical_pad = max(2, int(round(text_h * 0.18)))

    prior_mask = cv2.dilate(
        polygon_mask,
        cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (horizontal_pad * 2 + 1, vertical_pad * 2 + 1),
        ),
        iterations=1,
    )

    distance_to_prior = cv2.distanceTransform(
        (prior_mask == 0).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )

    binary_mask = (mask >= 32).astype(np.uint8)
    component_count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary_mask,
        8,
    )

    refined = np.zeros_like(mask)
    polygon_center_x = x + (w / 2.0)

    close_distance = max(3.0, text_h * 0.12)
    far_distance = max(8.0, text_h * 0.35)

    for label in range(1, component_count):
        component = labels == label
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area <= 0:
            continue

        comp_w = int(stats[label, cv2.CC_STAT_WIDTH])
        comp_h = int(stats[label, cv2.CC_STAT_HEIGHT])
        center_x, _ = centroids[label]

        overlap = int(np.count_nonzero(prior_mask[component]))
        overlap_ratio = overlap / area

        min_distance = float(distance_to_prior[component].min())
        mean_distance = float(distance_to_prior[component].mean())
        x_offset = abs(center_x - polygon_center_x) / text_w

        width_ratio = comp_w / text_w

        top = int(stats[label, cv2.CC_STAT_TOP])
        bottom = top + comp_h - 1
        overlap_top = max(top, band_top)
        overlap_bottom = min(bottom, band_bottom)
        band_overlap_height = max(0, overlap_bottom - overlap_top + 1)
        band_overlap_ratio = band_overlap_height / comp_h
        outside_band_height = comp_h - band_overlap_height
        relative_height = comp_h / band_height
        touches_edge = (
            top <= 2
            or bottom >= mask.shape[0] - 3
            or int(stats[label, cv2.CC_STAT_LEFT]) <= 2
            or int(stats[label, cv2.CC_STAT_LEFT]) + comp_w >= mask.shape[1] - 2
        )

        touches_prior = overlap > 0
        near_prior = min_distance <= close_distance
        within_reasonable_span = (
            comp_h / text_h <= 1.8
            and width_ratio <= 0.6
            and x_offset <= 0.9
        )
        far_and_tall = (
            min_distance > far_distance
            and relative_height >= 0.95
            and width_ratio <= 0.25
            and x_offset >= 0.45
        )
        stray_spike = (
            relative_height >= 1.15
            and width_ratio <= 0.22
            and x_offset >= 0.35
            and mean_distance > close_distance
            and outside_band_height >= max(8, int(round(band_height * 0.2)))
        )
        tiny_stray = (
            area <= 80
            and overlap_ratio < 0.2
            and band_overlap_ratio < 0.5
            and min_distance > close_distance
        )
        nearby_punctuation = (
            area <= 400
            and comp_h <= max(24, int(round(text_h * 0.45)))
            and width_ratio <= 0.16
            and x_offset <= 1.15
            and min_distance <= far_distance
            and not touches_edge
        )
        edge_tiny_stray = (
            area <= 400
            and touches_edge
            and width_ratio <= 0.12
            and (
                band_overlap_ratio <= 0.45
                or comp_h <= max(24, int(round(band_height * 0.18)))
            )
        )

        keep = (
            touches_prior
            or overlap_ratio >= 0.03
            or near_prior
            or (within_reasonable_span and min_distance <= far_distance)
        )

        if (
            far_and_tall
            or stray_spike
            or (tiny_stray and not nearby_punctuation)
            or edge_tiny_stray
        ):
            keep = False

        if keep:
            refined[component] = mask[component]

    kernel = np.ones((2, 2), np.uint8)
    refined = cv2.morphologyEx(refined, cv2.MORPH_CLOSE, kernel, iterations=1)
    return refined


def make_rgba(crop: np.ndarray, mask: np.ndarray) -> np.ndarray:
    bgra = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = mask
    return bgra


def composite_rgba(
    canvas: np.ndarray,
    rgba: np.ndarray,
    x: int,
    y: int,
) -> None:
    h, w = rgba.shape[:2]

    x2 = min(canvas.shape[1], x + w)
    y2 = min(canvas.shape[0], y + h)

    if x2 <= x or y2 <= y:
        return

    rgba = rgba[: y2 - y, : x2 - x]

    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0

    target = canvas[y:y2, x:x2].astype(np.float32)

    blended = rgb * alpha + target * (1.0 - alpha)

    canvas[y:y2, x:x2] = np.clip(blended, 0, 255).astype(np.uint8)


def sanitize_text(text: str, max_len: int = 40) -> str:
    sanitized = text.strip()
    for char in '<>:"/\\|?*':
        sanitized = sanitized.replace(char, "_")
    sanitized = " ".join(sanitized.split())
    return sanitized[:max_len] or "empty"


def extract_text_layers(options: ExtractionOptions) -> dict:
    options.output_dir.mkdir(parents=True, exist_ok=True)
    layers_dir = options.output_dir / "text_layers"
    layers_dir.mkdir(exist_ok=True)

    image = cv2.imread(str(options.image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Cannot read image: {options.image_path}")

    combined_mask = None
    preview = None
    reconstructed = None
    if options.debug_outputs:
        combined_mask, preview, reconstructed = create_debug_canvases(image)

    img_h, img_w = image.shape[:2]
    with open(options.json_path, "r", encoding="utf-8") as file:
        result = json.load(file)

    boxes = result["rec_boxes"]
    polys = result.get("rec_polys", boxes)
    texts = result["rec_texts"]
    scores = result["rec_scores"]
    layers = []
    layer_index = 0

    for detection_index, (box, poly, text, score) in enumerate(
        zip(boxes, polys, texts, scores)
    ):
        text = text.strip()
        if score < options.min_score or not text:
            continue

        x1, y1, x2, y2 = map(int, box)
        box_w = x2 - x1
        box_h = y2 - y1
        if box_w < 25 and box_h < 25:
            continue

        px1 = max(0, x1 - options.padding)
        py1 = max(0, y1 - options.padding)
        px2 = min(img_w, x2 + options.padding)
        py2 = min(img_h, y2 + options.padding)

        crop = image[py1:py2, px1:px2].copy()
        mask = estimate_text_mask(crop)
        if poly is not None:
            crop_poly = np.asarray(poly, dtype=np.float32).reshape(-1, 2)
            crop_poly[:, 0] -= px1
            crop_poly[:, 1] -= py1
            mask = refine_text_mask(mask, crop_poly)
            if not mask_has_expected_coverage(mask, crop_poly):
                fallback_mask = estimate_ocr_constrained_text_mask(crop, crop_poly)
                if np.any(fallback_mask >= 32):
                    mask = fallback_mask
        rgba = make_rgba(crop, mask)

        filename = f"text_{layer_index:03d}_{sanitize_text(text)}.png"
        output_path = layers_dir / filename
        cv2.imwrite(str(output_path), rgba)

        if options.debug_outputs:
            region = combined_mask[py1:py2, px1:px2]
            np.maximum(region, mask, out=region)

            composite_rgba(
                preview,
                rgba,
                px1,
                py1,
            )

            composite_rgba(
                reconstructed,
                rgba,
                px1,
                py1,
            )

        # ── 樣式推算 ──────────────────────────────────────────────────────
        style_hint = None
        if options.extract_style_hints:
            try:
                style_hint = estimate_style_from_rgba(
                    rgba,
                    ocr_box_height_px=box_h,
                    canvas_height_px=img_h,
                ).to_dict()
            except Exception:
                style_hint = None

        layer_entry = {
            "id": f"text_{layer_index:03d}",
            "type": "text",
            "file": str(output_path.relative_to(options.output_dir)),
            "text": text,
            "score": float(score),
            "ocr_box": [x1, y1, x2, y2],
            "x": px1,
            "y": py1,
            "width": px2 - px1,
            "height": py2 - py1,
            "source_detection_index": detection_index,
        }
        if style_hint is not None:
            layer_entry["style_hint"] = style_hint

        layers.append(layer_entry)

        print(f"[{layer_index:03d}] {score:.3f} {text}")
        layer_index += 1

    output_json = {
        "source_image": str(options.image_path),
        "source_ocr_json": str(options.json_path),
        "canvas": {"width": img_w, "height": img_h},
        "layer_count": len(layers),
        "layers": layers,
    }

    with open(options.output_dir / "layers.json", "w", encoding="utf-8") as file:
        json.dump(output_json, file, ensure_ascii=False, indent=2)

    if options.debug_outputs:
        cv2.imwrite(
            str(options.output_dir / "combined_text_mask.png"),
            combined_mask,
        )

        cv2.imwrite(
            str(options.output_dir / "preview_layers.png"),
            preview,
        )

        cv2.imwrite(
            str(options.output_dir / "reconstructed_text.png"),
            reconstructed,
        )

    print()
    print(f"Done: {len(layers)} text layers")
    print(f"Output: {options.output_dir}")
    return output_json
