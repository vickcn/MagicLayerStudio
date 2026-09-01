import shutil
import subprocess
from pathlib import Path
from typing import List, Union

try:
    from src.models.document import PageImage
except ModuleNotFoundError:
    from models.document import PageImage


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx"}


def load_pages(input_path: Path, work_dir: Path, pdf_dpi: int = 200) -> List[PageImage]:
    suffix = input_path.suffix.lower()

    if suffix in IMAGE_EXTENSIONS:
        return [PageImage(id="page_001", index=0, image_path=input_path)]

    if suffix == ".pdf":
        return _render_pdf_pages(input_path, work_dir / "pages", pdf_dpi)

    if suffix in PRESENTATION_EXTENSIONS:
        pdf_path = _convert_presentation_to_pdf(input_path, work_dir / "rendered_pdf")
        return _render_pdf_pages(pdf_path, work_dir / "pages", pdf_dpi)

    raise ValueError(f"Unsupported input type: {input_path}")


def load_document_pages(
    input_paths: Union[List[Path], Path],
    work_dir: Path,
    pdf_dpi: int = 200,
) -> List[PageImage]:
    if isinstance(input_paths, (str, Path)):
        input_paths = [Path(input_paths)]
    pages: List[PageImage] = []

    for input_path in input_paths:
        loaded_pages = load_pages(input_path, work_dir / input_path.stem, pdf_dpi)
        for page in loaded_pages:
            page_index = len(pages)
            pages.append(
                PageImage(
                    id=f"page_{page_index + 1:03d}",
                    index=page_index,
                    image_path=page.image_path,
                )
            )

    return pages


def _render_pdf_pages(pdf_path: Path, pages_dir: Path, dpi: int) -> List[PageImage]:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        try:
            import fitz
        except ImportError:
            raise RuntimeError("PDF/PPTX input requires PyMuPDF. Install it with: pip install pymupdf") from exc

    pages_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    pages: List[PageImage] = []

    for index, page in enumerate(doc):
        page_path = pages_dir / f"page_{index + 1:03d}.png"
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        pix.save(str(page_path))
        pages.append(PageImage(id=f"page_{index + 1:03d}", index=index, image_path=page_path))

    doc.close()
    return pages


def _convert_presentation_to_pdf(input_path: Path, output_dir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise RuntimeError("PPT/PPTX input requires LibreOffice command line tool: soffice")

    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            str(input_path),
            "--outdir",
            str(output_dir),
        ],
        check=True,
    )

    pdf_path = output_dir / f"{input_path.stem}.pdf"
    if not pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not create expected PDF: {pdf_path}")

    return pdf_path
