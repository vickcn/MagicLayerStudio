from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class LineGeometry:
    id: str
    text: str
    x: int
    y: int
    width: int
    height: int
    score: float = 0.0
    file: Optional[str] = None

    @property
    def left(self) -> int:
        return self.x

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def top(self) -> int:
        return self.y

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2.0


def line_geometry_from_layer(layer: dict) -> LineGeometry:
    return LineGeometry(
        id=str(layer["id"]),
        text=str(layer.get("text", "")),
        x=int(layer["x"]),
        y=int(layer["y"]),
        width=int(layer["width"]),
        height=int(layer["height"]),
        score=float(layer.get("score", 0.0)),
        file=layer.get("file"),
    )


def horizontal_overlap_ratio(a: LineGeometry, b: LineGeometry) -> float:
    overlap = max(0, min(a.right, b.right) - max(a.left, b.left))
    base = max(1, min(a.width, b.width))
    return overlap / base


def should_group(a: LineGeometry, b: LineGeometry) -> bool:
    upper, lower = (a, b) if (a.top, a.left) <= (b.top, b.left) else (b, a)

    avg_height = (upper.height + lower.height) / 2.0
    vertical_gap = lower.top - upper.bottom
    left_delta = abs(upper.left - lower.left)
    height_ratio = max(upper.height, lower.height) / max(
        1, min(upper.height, lower.height)
    )
    overlap_ratio = horizontal_overlap_ratio(upper, lower)
    vertical_overlap = max(
        0,
        min(upper.bottom, lower.bottom) - max(upper.top, lower.top),
    )
    vertical_overlap_ratio = vertical_overlap / max(
        1,
        min(upper.height, lower.height),
    )
    horizontal_gap = max(0, max(upper.left, lower.left) - min(upper.right, lower.right))

    if height_ratio > 1.35:
        return False

    same_row_fragment = vertical_overlap_ratio >= 0.45
    if same_row_fragment:
        return (
            horizontal_gap <= avg_height * 1.5
            or left_delta <= avg_height * 3.0
            or overlap_ratio >= 0.1
        )

    if vertical_gap > avg_height * 0.80:
        return False

    aligned = left_delta <= avg_height * 1.5
    overlapping = overlap_ratio >= 0.35

    return aligned or overlapping


def group_lines(lines: Sequence[LineGeometry]) -> list[list[LineGeometry]]:
    ordered = sorted(lines, key=lambda line: (line.top, line.left))
    if not ordered:
        return []

    adjacency: list[list[int]] = [[] for _ in ordered]

    for i, a in enumerate(ordered):
        for j in range(i + 1, len(ordered)):
            b = ordered[j]

            avg_height = (a.height + b.height) / 2.0
            if b.top - a.top > avg_height * 2.25:
                break

            if should_group(a, b):
                adjacency[i].append(j)
                adjacency[j].append(i)

    groups: list[list[LineGeometry]] = []
    visited = [False] * len(ordered)

    for start in range(len(ordered)):
        if visited[start]:
            continue

        stack = [start]
        visited[start] = True
        component: list[LineGeometry] = []

        while stack:
            node = stack.pop()
            component.append(ordered[node])

            for neighbor in adjacency[node]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    stack.append(neighbor)

        groups.append(sorted(component, key=lambda line: (line.top, line.left)))

    groups.sort(key=lambda group: (group[0].top, group[0].left))
    return groups


def _group_bbox(group: Sequence[LineGeometry]) -> tuple[int, int, int, int]:
    left = min(line.left for line in group)
    top = min(line.top for line in group)
    right = max(line.right for line in group)
    bottom = max(line.bottom for line in group)
    return left, top, right - left, bottom - top


def build_text_objects(
    layers: Sequence[dict],
) -> list[dict]:
    geoms = [line_geometry_from_layer(layer) for layer in layers]
    groups = group_lines(geoms)

    objects: list[dict] = []

    for index, group in enumerate(groups):
        x, y, width, height = _group_bbox(group)
        layer_ids = [line.id for line in group]
        texts = [line.text for line in group if line.text]
        scores = [line.score for line in group if line.score > 0]

        objects.append(
            {
                "id": f"text_object_{index:03d}",
                "type": "text_object",
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "layer_ids": layer_ids,
                "line_count": len(group),
                "text": "\n".join(texts),
                "score": float(np.mean(scores)) if scores else 0.0,
            }
        )

    return objects


def _create_checkerboard_canvas(height: int, width: int) -> np.ndarray:
    tile = 24
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    for y in range(0, height, tile):
        for x in range(0, width, tile):
            value = 220 if ((x // tile) + (y // tile)) % 2 == 0 else 180
            canvas[y : y + tile, x : x + tile] = value

    return canvas


def _composite_rgba(
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
    target = canvas[y:y2, x:x2]

    if target.shape[2] == 3:
        target_rgb = target.astype(np.float32)
        blended_rgb = rgb * alpha + target_rgb * (1.0 - alpha)
        canvas[y:y2, x:x2] = np.clip(blended_rgb, 0, 255).astype(np.uint8)
        return

    target_rgba = target.astype(np.float32)
    target_rgb = target_rgba[:, :, :3]
    target_alpha = target_rgba[:, :, 3:4] / 255.0
    out_alpha = alpha + target_alpha * (1.0 - alpha)

    safe_alpha = np.where(out_alpha > 0, out_alpha, 1.0)
    out_rgb = (
        rgb * alpha
        + target_rgb * target_alpha * (1.0 - alpha)
    ) / safe_alpha

    blended = np.concatenate(
        [
            np.clip(out_rgb, 0, 255),
            np.clip(out_alpha * 255.0, 0, 255),
        ],
        axis=2,
    )
    canvas[y:y2, x:x2] = blended.astype(np.uint8)


def compose_text_object_layers(
    output_dir: Path,
    layers: Sequence[dict],
    objects: Sequence[dict],
) -> list[dict]:
    text_objects_dir = output_dir / "text_objects"
    text_objects_dir.mkdir(exist_ok=True)

    layer_by_id = {str(layer["id"]): layer for layer in layers}
    composed_objects: list[dict] = []

    for obj in objects:
        width = int(obj["width"])
        height = int(obj["height"])
        object_canvas = np.zeros((height, width, 4), dtype=np.uint8)
        object_x = int(obj["x"])
        object_y = int(obj["y"])
        object_layers: list[dict] = []

        for layer_id in obj["layer_ids"]:
            layer = layer_by_id[layer_id]
            rgba = cv2.imread(
                str(output_dir / str(layer["file"])),
                cv2.IMREAD_UNCHANGED,
            )
            if rgba is None:
                continue

            local_x = int(layer["x"]) - object_x
            local_y = int(layer["y"]) - object_y
            _composite_rgba(object_canvas, rgba, local_x, local_y)
            object_layers.append(
                {
                    "id": layer_id,
                    "x": local_x,
                    "y": local_y,
                    "width": int(layer["width"]),
                    "height": int(layer["height"]),
                    "file": str(layer["file"]),
                }
            )

        file_name = f'{obj["id"]}.png'
        file_path = text_objects_dir / file_name
        cv2.imwrite(str(file_path), object_canvas)

        composed_object = dict(obj)
        composed_object["file"] = str(file_path.relative_to(output_dir))
        composed_object["object_layers"] = object_layers
        composed_objects.append(composed_object)

    return composed_objects


def render_grouped_objects_preview(
    output_dir: Path,
    layers: Sequence[dict],
    objects: Sequence[dict],
    canvas_size: tuple[int, int],
) -> np.ndarray:
    height, width = canvas_size
    preview = _create_checkerboard_canvas(height, width)

    for layer in layers:
        file_path = output_dir / str(layer["file"])
        rgba = cv2.imread(str(file_path), cv2.IMREAD_UNCHANGED)
        if rgba is None:
            continue
        _composite_rgba(preview, rgba, int(layer["x"]), int(layer["y"]))

    palette = [
        (46, 76, 255),
        (34, 197, 94),
        (249, 115, 22),
        (168, 85, 247),
        (236, 72, 153),
        (14, 165, 233),
    ]

    for index, obj in enumerate(objects):
        color = palette[index % len(palette)]
        x = int(obj["x"])
        y = int(obj["y"])
        w = int(obj["width"])
        h = int(obj["height"])

        cv2.rectangle(preview, (x, y), (x + w, y + h), color, 3)
        label = f"#{index}"
        label_y = max(24, y - 10)
        cv2.putText(
            preview,
            label,
            (x + 4, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            3,
            cv2.LINE_AA,
        )

    return preview
