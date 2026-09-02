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

# 超寬文字
# ↓
# 超寬 + 超高 ROI
# def build_object_roi(
#         obj: dict,
#         image_size: tuple[int, int],
#         min_padding: int = 96,
#         max_padding: int = 384,
#         target_aspect_ratio: float = 1.5,
#     ) -> ROI:
#     image_width, image_height = image_size

#     x = int(obj["x"])
#     y = int(obj["y"])
#     width = int(obj["width"])
#     height = int(obj["height"])

#     # 基本 padding 主要依文字高度，不依超寬 width
#     base_padding = round(height * 0.6)
#     base_padding = max(
#         min_padding,
#         min(max_padding, base_padding),
#     )

#     x1 = max(0, x - base_padding)
#     x2 = min(image_width, x + width + base_padding)

#     y1 = max(0, y - base_padding)
#     y2 = min(image_height, y + height + base_padding)

#     roi_width = x2 - x1
#     roi_height = y2 - y1

#     # 超寬 ROI：優先增加上下 context
#     desired_height = int(
#         roi_width / target_aspect_ratio
#     )

#     if desired_height > roi_height:
#         extra = desired_height - roi_height

#         top_extra = extra // 2
#         bottom_extra = extra - top_extra

#         y1 = max(0, y1 - top_extra)
#         y2 = min(
#             image_height,
#             y2 + bottom_extra,
#         )

#     return ROI(
#         x1=x1,
#         y1=y1,
#         x2=x2,
#         y2=y2,
#     )


def build_object_roi(
    obj: dict,
    image_size: tuple[int, int],
    min_padding: int = 96,
    max_padding: int = 256,
) -> ROI:

    image_width, image_height = image_size

    x = int(obj["x"])
    y = int(obj["y"])
    width = int(obj["width"])
    height = int(obj["height"])

    base_padding = round(
        height * 0.5
    )

    base_padding = max(
        min_padding,
        min(
            max_padding,
            base_padding,
        ),
    )

    return ROI(
        x1=max(
            0,
            x - base_padding,
        ),
        y1=max(
            0,
            y - base_padding,
        ),
        x2=min(
            image_width,
            x + width + base_padding,
        ),
        y2=min(
            image_height,
            y + height + base_padding,
        ),
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