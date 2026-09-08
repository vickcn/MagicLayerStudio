from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class PageImage:
    id: str
    index: int
    image_path: Path


@dataclass(frozen=True)
class PipelineOptions:
    min_score: float = 0.50
    padding: int = 8
    debug_outputs: bool = True
    dilate_kernel_size: int = 31
    inpaint_radius: int = 5
    inpaint_backend: str = "telea"
    harmonize: bool = True
    ocr_lang: str = "ch"
    pdf_dpi: int = 120
    work_dir: Optional[Path] = None
    rebuild_pptx: bool = True
    rebuilt_pptx_path: Optional[Path] = None
    extract_style_hints: bool = True   # 推算文字圖層樣式提示
    source_pptx_path: Optional[Path] = None  # 如果來源是 PPTX，用於讀取原始字型


@dataclass(frozen=True)
class PageResult:
    page: PageImage
    output_dir: Path
    layers_json: Path
    objects_json: Path
    background_path: Optional[Path]


@dataclass(frozen=True)
class DocumentResult:
    source_path: Path
    source_type: str
    output_dir: Path
    pages: List[PageResult]
    rebuilt_pptx_path: Optional[Path] = None
