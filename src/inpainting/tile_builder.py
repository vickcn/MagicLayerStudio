from __future__ import annotations

from PIL import Image


def build_tiles(
    roi_width: int,
    roi_height: int,
    tile_size: int = 768,
    overlap: int = 128,
) -> list[tuple[int, int, int, int]]:
    if overlap >= tile_size:
        raise ValueError(
            "overlap must be smaller than tile_size"
        )

    step = tile_size - overlap
    tiles = []

    y_positions = list(
        range(0, max(1, roi_height - tile_size + 1), step)
    )

    x_positions = list(
        range(0, max(1, roi_width - tile_size + 1), step)
    )

    # 補最後一塊，確保覆蓋邊界
    if roi_width > tile_size:
        last_x = roi_width - tile_size
        if not x_positions or x_positions[-1] != last_x:
            x_positions.append(last_x)

    if roi_height > tile_size:
        last_y = roi_height - tile_size
        if not y_positions or y_positions[-1] != last_y:
            y_positions.append(last_y)

    if roi_width <= tile_size:
        x_positions = [0]

    if roi_height <= tile_size:
        y_positions = [0]

    for y1 in y_positions:
        for x1 in x_positions:
            x2 = min(
                roi_width,
                x1 + tile_size,
            )
            y2 = min(
                roi_height,
                y1 + tile_size,
            )

            tiles.append(
                (x1, y1, x2, y2)
            )

    return tiles


def filter_tiles_by_mask(
    tiles: list[tuple[int, int, int, int]],
    mask: Image.Image,
) -> list[tuple[int, int, int, int]]:
    result = []

    for tile in tiles:
        tile_mask = mask.crop(tile)

        if tile_mask.getbbox() is not None:
            result.append(tile)

    return result