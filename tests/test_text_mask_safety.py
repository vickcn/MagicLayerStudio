"""Regression tests for the local pipeline's text and inpainting masks."""

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.inpainting.classical_inpainting import create_conservative_inpaint_mask
from src.models.document import PipelineOptions
from src.text_layer_extractor import estimate_ocr_constrained_text_mask


class TextMaskSafetyTest(unittest.TestCase):
    def test_ocr_constrained_fallback_keeps_white_outlined_text_on_varied_background(self):
        image = np.zeros((64, 240, 3), dtype=np.uint8)
        for x in range(image.shape[1]):
            image[:, x] = (40 + x // 4, 30 + x // 7, 120 + x // 8)

        cv2.putText(image, "HELLO", (34, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 4, cv2.LINE_AA)
        cv2.putText(image, "HELLO", (34, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        polygon = np.array([[30, 20], [140, 20], [140, 48], [30, 48]], dtype=np.float32)

        alpha = estimate_ocr_constrained_text_mask(image, polygon)

        self.assertGreater(np.count_nonzero(alpha >= 32), 300)
        self.assertGreater(int(alpha[35, 48]), 0)

    def test_conservative_inpaint_mask_caps_legacy_large_kernel(self):
        text_alpha = np.zeros((80, 120), dtype=np.uint8)
        text_alpha[35:40, 50:70] = 255

        mask, effective_kernel = create_conservative_inpaint_mask(text_alpha, kernel_size=31)

        self.assertEqual(effective_kernel, 7)
        self.assertEqual(mask[0, 0], 0)
        self.assertLess(np.count_nonzero(mask), 1_000)

    def test_local_pipeline_uses_safe_inpainting_defaults(self):
        self.assertEqual(PipelineOptions().dilate_kernel_size, 3)
        self.assertEqual(PipelineOptions().inpaint_radius, 1)


if __name__ == "__main__":
    unittest.main()
