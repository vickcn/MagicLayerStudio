from __future__ import annotations

from pathlib import Path

from PIL import (
    Image,
    ImageFilter,
)


MODEL_ID = (
    "stable-diffusion-v1-5/"
    "stable-diffusion-inpainting"
)


class SDInpainter:
    def __init__(
        self,
        model_id: str = MODEL_ID,
    ) -> None:
        try:
            import torch
            from diffusers import StableDiffusionInpaintPipeline
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "SD backend requires torch and diffusers in the active environment."
            ) from exc

        if torch.backends.mps.is_available():
            self.device = "mps"
            # dtype = torch.float16
            dtype = torch.float32

        elif torch.cuda.is_available():
            self.device = "cuda"
            dtype = torch.float16

        else:
            self.device = "cpu"
            dtype = torch.float32

        print(
            f"[SD] loading model on {self.device}"
        )

        # self.pipe = (
        #     StableDiffusionInpaintPipeline
        #     .from_pretrained(
        #         model_id,
        #         dtype=dtype,
        #     )
        # )
        self.pipe = StableDiffusionInpaintPipeline.from_pretrained(
            model_id,
            dtype=dtype,
            safety_checker=None,
            requires_safety_checker=False,
        )

        self.pipe = self.pipe.to(
            self.device
        )

        if self.device == "mps":
            self.pipe.enable_attention_slicing()

        print("[SD] model ready")

    def inpaint(
        self,
        image: Image.Image,
        mask: Image.Image,
        prompt: str | None = None,
        negative_prompt: str | None = None,
        steps: int = 25,
        guidance_scale: float = 5.0,
        max_dimension: int = 768,
        mask_expand_radius: int = 16,
    ) -> Image.Image:

        image = image.convert("RGB")
        mask = mask.convert("L")

        # SD 專用 mask expansion。
        # 必須連同文字的 outline / shadow / glow 一起移除，
        # 否則 diffusion 容易重新生成文字輪廓。
        kernel_size = mask_expand_radius * 2 + 1
        mask = mask.filter(
            ImageFilter.MaxFilter(kernel_size)
        )

        original_size = image.size

        if prompt is None:
            prompt = (
                "naturally continue the surrounding "
                "background, preserve the original "
                "lighting, texture, colors and structure, "
                "clean background, no text"
            )

        if negative_prompt is None:
            negative_prompt = (
                "text, letters, typography, watermark, "
                "logo, symbols, blur, smudge, distortion, "
                "new objects"
            )

        prepared_image, prepared_mask = (
            self._prepare_for_model(
                image,
                mask,
                max_dimension=max_dimension,
            )
        )

        result = self.pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=prepared_image,
            mask_image=prepared_mask,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
        ).images[0]

        result = result.resize(
            original_size,
            Image.Resampling.LANCZOS,
        )

        return self._blend_result(
            original=image,
            generated=result,
            mask=mask,
        )

    def _prepare_for_model(
        self,
        image: Image.Image,
        mask: Image.Image,
        max_dimension: int,
    ):
        width, height = image.size

        scale = min(
            1.0,
            max_dimension / max(width, height),
        )
        
        width = round(width * scale)
        height = round(height * scale)

        # Stable Diffusion 尺寸最好為 8 的倍數
        width = max(
            64,
            (width // 8) * 8,
        )

        height = max(
            64,
            (height // 8) * 8,
        )

        image = image.resize(
            (width, height),
            Image.Resampling.LANCZOS,
        )

        mask = mask.resize(
            (width, height),
            Image.Resampling.NEAREST,
        )

        return image, mask

    def _blend_result(
        self,
        original: Image.Image,
        generated: Image.Image,
        mask: Image.Image,
    ) -> Image.Image:

        # 不讓 diffusion 改動 ROI 裡沒被 mask 的背景
        blend_mask = mask.convert("L")

        # 微微 feather，避免貼回去出現硬邊
        blend_mask = blend_mask.filter(
            ImageFilter.GaussianBlur(
                radius=5
            )
        )

        return Image.composite(
            generated,
            original,
            blend_mask,
        )
