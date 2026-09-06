from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


class BackgroundHarmonizer:
    """
    Harmonize repaired ROI with surrounding background.

    v2 Architecture (Pure Background Sampling):
    -------------------------------------------
    ✓ Transition band extraction from unmasked clean background
    ✓ Local & Global 2D Illumination gradient plane fitting (_match_illumination)
    ✓ Perceptual Lab color & distribution matching (_match_lab_statistics)
    ✓ Inpainting artifact smoothing / flattening (_smooth_residual)
    ✓ Synthetic high-frequency noise matching from background statistics (_match_noise)
    ✓ Distance-transform adaptive feathering to untouched background (_edge_feather)
    ✓ Optional Poisson gradient blending (_poisson_blend)
    """

    def __init__(
        self,
        feather_radius: int = 8,
        transition_width: int = 24,
        enable_illumination: bool = True,
        enable_color: bool = True,
        enable_smooth: bool = True,
        enable_contrast: bool = False,
        enable_noise: bool = True,
        enable_feather: bool = True,
        enable_poisson: bool = False,
        noise_strength: float = 0.3,
        feather_mode: str = "distance",
    ):
        self.feather_radius = feather_radius
        self.transition_width = transition_width
        self.enable_illumination = enable_illumination
        self.enable_color = enable_color
        self.enable_smooth = enable_smooth
        self.enable_contrast = enable_contrast
        self.enable_noise = enable_noise
        self.enable_feather = enable_feather
        self.enable_poisson = enable_poisson
        self.noise_strength = noise_strength
        self.feather_mode = feather_mode

    def harmonize(
        self,
        original: Image.Image,
        repaired: Image.Image,
        mask: Image.Image,
    ) -> Image.Image:
        original_arr = np.asarray(
            original.convert("RGB"),
            dtype=np.float32,
        )

        repaired_arr = np.asarray(
            repaired.convert("RGB"),
            dtype=np.float32,
        )

        mask_arr = np.asarray(
            mask.convert("L"),
            dtype=np.uint8,
        )

        # Threshold mask to strictly binary
        mask_binary = (mask_arr > 127).astype(np.uint8) * 255
        if mask_binary.sum() == 0:
            return repaired

        # 1. 2D Illumination gradient plane matching
        if self.enable_illumination:
            repaired_arr = self._match_illumination(
                original_arr,
                repaired_arr,
                mask_binary,
            )

        # 2. Lab color & tone distribution matching
        if self.enable_color:
            repaired_arr = self._match_lab_statistics(
                original_arr,
                repaired_arr,
                mask_binary,
            )
        elif self.enable_contrast:
            repaired_arr = self._match_contrast(
                original_arr,
                repaired_arr,
                mask_binary,
            )

        # 3. Smooth inpaint brush ripples / artifacts
        if self.enable_smooth:
            repaired_arr = self._smooth_residual(
                repaired_arr,
                mask_binary,
            )

        # 4. High-frequency background noise matching (synthetic noise based on background band)
        if self.enable_noise:
            repaired_arr = self._match_noise(
                original_arr,
                repaired_arr,
                mask_binary,
            )

        # 5. Adaptive feather blending with original clean background
        if self.enable_feather:
            repaired_arr = self._edge_feather(
                original_arr,
                repaired_arr,
                mask_binary,
            )

        # 6. Poisson gradient blending (optional)
        if self.enable_poisson:
            repaired_arr = self._poisson_blend(
                original_arr,
                repaired_arr,
                mask_binary,
            )

        repaired_arr = np.clip(
            repaired_arr,
            0,
            255,
        ).astype(np.uint8)

        return Image.fromarray(repaired_arr)

    # --------------------------------------------------
    # Transition Band
    # --------------------------------------------------

    def _build_transition_band(
        self,
        mask: np.ndarray,
        width: int | None = None,
    ) -> np.ndarray:
        w = width if width is not None else self.transition_width
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (w * 2 + 1, w * 2 + 1),
        )
        outer = cv2.dilate(mask, kernel)
        band = cv2.subtract(outer, mask)
        return band > 0

    # --------------------------------------------------
    # Illumination Plane Fitting
    # --------------------------------------------------

    def _estimate_light_plane(
        self,
        values: np.ndarray,
        ys: np.ndarray,
        xs: np.ndarray,
    ) -> tuple[float, float, float]:
        """Fit a 2D plane: v(x, y) = a*x + b*y + c using least squares."""
        if len(xs) < 3:
            mean_val = float(np.mean(values)) if len(values) > 0 else 0.0
            return 0.0, 0.0, mean_val

        A = np.stack(
            [
                xs.astype(np.float64),
                ys.astype(np.float64),
                np.ones_like(xs, dtype=np.float64),
            ],
            axis=1,
        )
        try:
            coef, _, _, _ = np.linalg.lstsq(A, values.astype(np.float64), rcond=None)
            return float(coef[0]), float(coef[1]), float(coef[2])
        except Exception:
            return 0.0, 0.0, float(np.mean(values))

    def _match_illumination(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Fit 2D gradient illumination plane using clean background around the mask,
        and blend the fitted smooth gradient into the inpainting region to eliminate
        brush/diffusion artifacts.
        """
        roi = mask > 0
        band = self._build_transition_band(mask)
        if roi.sum() == 0 or band.sum() == 0:
            return repaired

        ys_band, xs_band = np.where(band)
        ys_roi, xs_roi = np.where(roi)

        result = repaired.copy()

        for c in range(3):
            orig_band_vals = original[ys_band, xs_band, c]
            a_orig, b_orig, c_orig = self._estimate_light_plane(orig_band_vals, ys_band, xs_band)

            # Target smooth plane across the inpaint region
            target_plane = a_orig * xs_roi + b_orig * ys_roi + c_orig

            # Blend fitted smooth plane with repaired values (70% plane, 30% repaired)
            result[ys_roi, xs_roi, c] = (
                0.75 * target_plane + 0.25 * repaired[ys_roi, xs_roi, c]
            )

        return result

    # --------------------------------------------------
    # Lab Color & Tone Distribution
    # --------------------------------------------------

    def _match_lab_statistics(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        band = self._build_transition_band(mask)
        roi = mask > 0

        if roi.sum() == 0 or band.sum() == 0:
            return repaired

        orig_clip = np.clip(original, 0, 255).astype(np.uint8)
        rep_clip = np.clip(repaired, 0, 255).astype(np.uint8)

        orig_lab = cv2.cvtColor(orig_clip, cv2.COLOR_RGB2LAB).astype(np.float32)
        rep_lab = cv2.cvtColor(rep_clip, cv2.COLOR_RGB2LAB).astype(np.float32)

        for c in range(3):
            band_mean = orig_lab[band, c].mean()
            band_std = max(float(orig_lab[band, c].std()), 0.5)

            roi_mean = rep_lab[roi, c].mean()
            roi_std = max(float(rep_lab[roi, c].std()), 0.5)

            # Gently shift mean and adjust variance towards background
            rep_roi = (rep_lab[roi, c] - roi_mean) * (band_std / roi_std) + band_mean
            rep_lab[roi, c] = 0.8 * rep_roi + 0.2 * rep_lab[roi, c]

        rep_lab = np.clip(rep_lab, 0, 255).astype(np.uint8)
        repaired_rgb = cv2.cvtColor(rep_lab, cv2.COLOR_LAB2RGB).astype(np.float32)

        repaired[roi] = repaired_rgb[roi]
        return repaired

    # --------------------------------------------------
    # Contrast Matching
    # --------------------------------------------------

    def _match_contrast(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        roi = mask > 0
        band = self._build_transition_band(mask)

        if roi.sum() == 0 or band.sum() == 0:
            return repaired

        band_mean = original[band].mean(axis=0)
        band_std = np.maximum(original[band].std(axis=0), 1.0)

        roi_mean = repaired[roi].mean(axis=0)
        roi_std = np.maximum(repaired[roi].std(axis=0), 1.0)

        repaired_roi = repaired[roi]
        repaired_roi = (repaired_roi - roi_mean) * (band_std / roi_std) + band_mean

        repaired[roi] = repaired_roi
        return repaired

    # --------------------------------------------------
    # Surface Residual Smoothing
    # --------------------------------------------------

    def _smooth_residual(
        self,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """Flatten inpainting brush/diffusion ripples inside mask using surface blur."""
        roi = mask > 0
        if roi.sum() == 0:
            return repaired

        # Find bounding box of mask to avoid expensive full-image filtering
        ys, xs = np.where(roi)
        ymin, ymax = max(0, int(ys.min()) - 10), min(repaired.shape[0], int(ys.max()) + 11)
        xmin, xmax = max(0, int(xs.min()) - 10), min(repaired.shape[1], int(xs.max()) + 11)

        sub_rep = repaired[ymin:ymax, xmin:xmax]
        sub_mask = mask[ymin:ymax, xmin:xmax] > 0

        sub_u8 = np.clip(sub_rep, 0, 255).astype(np.uint8)
        smoothed = cv2.bilateralFilter(sub_u8, d=9, sigmaColor=35, sigmaSpace=35).astype(np.float32)

        sub_rep[sub_mask] = smoothed[sub_mask]
        repaired[ymin:ymax, xmin:xmax] = sub_rep
        return repaired

    # --------------------------------------------------
    # High-Frequency Noise Matching (Synthetic from background band)
    # --------------------------------------------------

    def _match_noise(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        roi = mask > 0
        band = self._build_transition_band(mask)
        if roi.sum() == 0 or band.sum() == 0:
            return repaired

        # Extract background high frequency noise only from unmasked band
        blur = cv2.GaussianBlur(original, (0, 0), sigmaX=3.0)
        bg_noise = original[band] - blur[band]

        noise_std = np.std(bg_noise, axis=0)  # shape (3,)

        # Only inject if background actually has noticeable grain
        if np.mean(noise_std) > 0.5:
            num_roi_pixels = roi.sum()
            synthetic_noise = np.random.normal(
                loc=0.0,
                scale=noise_std * self.noise_strength,
                size=(num_roi_pixels, 3),
            ).astype(np.float32)

            repaired[roi] += synthetic_noise

        return repaired

    # --------------------------------------------------
    # Adaptive Feather Blending
    # --------------------------------------------------

    def _distance_alpha(
        self,
        mask: np.ndarray,
    ) -> np.ndarray:
        if self.feather_mode == "distance":
            dist = cv2.distanceTransform(
                mask,
                cv2.DIST_L2,
                5,
            )
            radius = max(float(self.feather_radius), 1.0)
            alpha = np.clip(dist / radius, 0.0, 1.0)
        else:
            alpha = cv2.GaussianBlur(
                mask.astype(np.float32) / 255.0,
                (0, 0),
                self.feather_radius,
            )

        return alpha[..., None]

    def _edge_feather(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Blend repaired region with original outside mask.
        Inside mask: alpha = 1 (100% repaired).
        Outside mask: alpha = 0 (100% original).
        At border: smooth gradient.
        """
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self.feather_radius * 2 + 1, self.feather_radius * 2 + 1),
        )
        dilated_mask = cv2.dilate(mask, kernel)

        soft_mask = cv2.GaussianBlur(
            dilated_mask.astype(np.float32) / 255.0,
            (0, 0),
            sigmaX=max(float(self.feather_radius) / 2.0, 1.0),
        )[..., None]

        return repaired * soft_mask + original * (1.0 - soft_mask)

    # --------------------------------------------------
    # Poisson Gradient Blending
    # --------------------------------------------------

    def _poisson_blend(
        self,
        original: np.ndarray,
        repaired: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return repaired

        # Crop to bounding box with margin for speed
        pad = 20
        ymin, ymax = max(0, int(ys.min()) - pad), min(repaired.shape[0], int(ys.max()) + pad)
        xmin, xmax = max(0, int(xs.min()) - pad), min(repaired.shape[1], int(xs.max()) + pad)

        sub_orig = np.clip(original[ymin:ymax, xmin:xmax], 0, 255).astype(np.uint8)
        sub_rep = np.clip(repaired[ymin:ymax, xmin:xmax], 0, 255).astype(np.uint8)
        sub_mask = np.clip(mask[ymin:ymax, xmin:xmax], 0, 255).astype(np.uint8)

        center = (
            sub_rep.shape[1] // 2,
            sub_rep.shape[0] // 2,
        )

        try:
            blended = cv2.seamlessClone(
                sub_rep,
                sub_orig,
                sub_mask,
                center,
                cv2.NORMAL_CLONE,
            )
            repaired[ymin:ymax, xmin:xmax] = blended.astype(np.float32)
            return repaired
        except Exception:
            return repaired