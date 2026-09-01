from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class ROI:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


def build_object_roi(
    obj: dict,
    image_size: tuple[int, int],
    padding_ratio: float = 0.30,
    min_padding: int = 80,
    max_padding: int = 300,
) -> ROI:
    image_width, image_height = image_size

    x = int(obj["x"])
    y = int(obj["y"])
    width = int(obj["width"])
    height = int(obj["height"])

    # 依文字物件高度決定需要多少背景 context
    padding = round(
        max(width, height) * padding_ratio
    )

    padding = max(
        min_padding,
        min(max_padding, padding),
    )

    x1 = max(0, x - padding)
    y1 = max(0, y - padding)

    x2 = min(
        image_width,
        x + width + padding,
    )

    y2 = min(
        image_height,
        y + height + padding,
    )

    return ROI(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
    )


def crop_roi(
    image: Image.Image,
    mask: Image.Image,
    roi: ROI,
) -> tuple[Image.Image, Image.Image]:
    box = (
        roi.x1,
        roi.y1,
        roi.x2,
        roi.y2,
    )

    return (
        image.crop(box),
        mask.crop(box),
    )