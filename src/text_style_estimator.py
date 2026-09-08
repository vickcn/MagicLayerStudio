"""
text_style_estimator.py
從文字圖層的 RGBA 裁切圖像推算文字樣式屬性。
純 CV 計算，不依賴 OCR 或外部 API。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class StyleHint:
    """從圖像推算出的文字樣式提示，供重組 PPTX 時使用。"""
    dominant_color_rgb: Tuple[int, int, int]   # 文字主色 (R, G, B)
    estimated_font_size_pt: float              # 估算字型大小（點）
    likely_bold: bool                          # 是否可能為粗體
    stroke_color_rgb: Optional[Tuple[int, int, int]] = None  # 描邊色（如能推算）
    font_name_hint: Optional[str] = None       # 字體提示（來自外部對映，非推算）

    def to_dict(self) -> dict:
        return {
            "dominant_color_rgb": list(self.dominant_color_rgb),
            "estimated_font_size_pt": round(self.estimated_font_size_pt, 1),
            "likely_bold": self.likely_bold,
            "stroke_color_rgb": list(self.stroke_color_rgb) if self.stroke_color_rgb else None,
            "font_name_hint": self.font_name_hint,
        }


# ── 常數 ─────────────────────────────────────────────────────────────────────
# PPT 標準 slide 尺寸（inches）
_SLIDE_WIDTH_IN = 13.333333
_SLIDE_HEIGHT_IN = 7.5
_PT_PER_IN = 72.0

# 字型大小估算比例（OCR box 高度的比例）
# 中文字通常佔 box 高度的 70–85%
_FONT_SIZE_RATIO = 0.72

# 粗體判斷：前景像素的「筆劃密度」高於此閾值 → 推判為粗體
_BOLD_DENSITY_THRESHOLD = 0.22


# ── 核心函式 ──────────────────────────────────────────────────────────────────

def estimate_style_from_rgba(
    rgba: np.ndarray,
    ocr_box_height_px: int,
    canvas_height_px: int,
    slide_height_in: float = _SLIDE_HEIGHT_IN,
) -> StyleHint:
    """
    從 RGBA 前景圖層推算字體樣式。

    Parameters
    ----------
    rgba : np.ndarray
        shape (H, W, 4)，BGRA 或 RGBA 格式均可（此處假設 BGRA，與 OpenCV 一致）
    ocr_box_height_px : int
        OCR 偵測框高度（像素），用於推算字型大小
    canvas_height_px : int
        原始頁面圖像總高度（像素）
    slide_height_in : float
        目標 PPTX 頁面高度（英吋），預設 7.5 in

    Returns
    -------
    StyleHint
    """
    if rgba is None or rgba.size == 0:
        return _fallback_hint(ocr_box_height_px, canvas_height_px, slide_height_in)

    h, w = rgba.shape[:2]
    if h == 0 or w == 0:
        return _fallback_hint(ocr_box_height_px, canvas_height_px, slide_height_in)

    # alpha channel
    if rgba.shape[2] == 4:
        alpha = rgba[:, :, 3]
        bgr = rgba[:, :, :3]
    else:
        # 如果沒有 alpha channel，用灰階估 mask
        bgr = rgba[:, :, :3]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, alpha = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # ── 1. 主色（有效前景像素的中位數 BGR） ──────────────────────────────
    fg_mask = alpha > 128
    fg_count = np.count_nonzero(fg_mask)

    if fg_count < 10:
        dominant_rgb = (255, 255, 255)
    else:
        fg_pixels = bgr[fg_mask]  # shape (N, 3), BGR
        median_bgr = np.median(fg_pixels, axis=0).astype(int)
        # 轉成 RGB
        dominant_rgb = (int(median_bgr[2]), int(median_bgr[1]), int(median_bgr[0]))

    # ── 2. 字型大小估算 ───────────────────────────────────────────────────
    slide_height_pt = slide_height_in * _PT_PER_IN
    font_size_pt = ocr_box_height_px / canvas_height_px * slide_height_pt * _FONT_SIZE_RATIO
    font_size_pt = max(6.0, min(font_size_pt, 400.0))

    # ── 3. 粗體推算（筆劃密度） ───────────────────────────────────────────
    if fg_count > 0:
        density = fg_count / (h * w)
        likely_bold = density > _BOLD_DENSITY_THRESHOLD
    else:
        likely_bold = False

    # ── 4. 描邊色推算（若前景邊緣有明顯不同色） ─────────────────────────
    stroke_color = _estimate_stroke_color(bgr, alpha, dominant_rgb)

    return StyleHint(
        dominant_color_rgb=dominant_rgb,
        estimated_font_size_pt=round(font_size_pt, 1),
        likely_bold=likely_bold,
        stroke_color_rgb=stroke_color,
    )


def estimate_style_from_file(
    rgba_path: Path,
    ocr_box_height_px: int,
    canvas_height_px: int,
    slide_height_in: float = _SLIDE_HEIGHT_IN,
) -> StyleHint:
    """從檔案路徑讀入 RGBA PNG 後進行估算。"""
    img = cv2.imread(str(rgba_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return _fallback_hint(ocr_box_height_px, canvas_height_px, slide_height_in)
    return estimate_style_from_rgba(img, ocr_box_height_px, canvas_height_px, slide_height_in)


# ── 輔助函式 ──────────────────────────────────────────────────────────────────

def _fallback_hint(
    ocr_box_height_px: int,
    canvas_height_px: int,
    slide_height_in: float,
) -> StyleHint:
    slide_height_pt = slide_height_in * _PT_PER_IN
    font_size_pt = max(
        8.0,
        ocr_box_height_px / max(canvas_height_px, 1) * slide_height_pt * _FONT_SIZE_RATIO,
    )
    return StyleHint(
        dominant_color_rgb=(255, 255, 255),
        estimated_font_size_pt=round(font_size_pt, 1),
        likely_bold=False,
    )


def _estimate_stroke_color(
    bgr: np.ndarray,
    alpha: np.ndarray,
    fill_rgb: Tuple[int, int, int],
) -> Optional[Tuple[int, int, int]]:
    """
    嘗試從半透明邊緣區域推算描邊色。
    只有在「邊緣像素主色」與填色差距夠大時才回傳，否則回傳 None。
    """
    # 邊緣：alpha 在 32–180 之間的像素（羽化邊緣）
    edge_mask = (alpha >= 32) & (alpha <= 180)
    if np.count_nonzero(edge_mask) < 20:
        return None

    edge_pixels = bgr[edge_mask]
    median_bgr = np.median(edge_pixels, axis=0).astype(int)
    edge_rgb = (int(median_bgr[2]), int(median_bgr[1]), int(median_bgr[0]))

    # 計算與填色的 L2 距離
    fill_arr = np.array(fill_rgb, dtype=float)
    edge_arr = np.array(edge_rgb, dtype=float)
    dist = np.linalg.norm(fill_arr - edge_arr)

    # 距離夠大才視為有描邊
    if dist > 60:
        return edge_rgb
    return None
