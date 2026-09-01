from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Union

try:
    from src.inputs.document_loader import (
        load_document_pages,
    )
    from src.models.document import (
        DocumentResult,
        PipelineOptions,
    )
    from src.pipeline.page_pipeline import (
        process_page,
    )
    from src.pptx_rebuilder import (
        rebuild_pptx_from_document,
    )
except ModuleNotFoundError:
    from inputs.document_loader import (
        load_document_pages,
    )
    from models.document import (
        DocumentResult,
        PipelineOptions,
    )
    from pipeline.page_pipeline import (
        process_page,
    )
    from pptx_rebuilder import (
        rebuild_pptx_from_document,
    )


def process_document(
    input_paths: Union[List[Path], Path],
    output_dir: Path,
    options: Optional[PipelineOptions] = None,
) -> DocumentResult:
    if options is None:
        options = PipelineOptions()

    if isinstance(input_paths, (str, Path)):
        resolved_inputs = [Path(input_paths).resolve()]
    else:
        resolved_inputs = [Path(p).resolve() for p in input_paths]

    if not resolved_inputs:
        raise ValueError("No input paths provided")

    primary_input = resolved_inputs[0]
    document_name = primary_input.stem

    if len(resolved_inputs) > 1 or output_dir.name in ("output_document", "output", "tmp", "output_layers"):
        document_dir = output_dir / document_name
    else:
        document_dir = output_dir

    document_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    work_dir = options.work_dir or (document_dir / "_work")

    pages = load_document_pages(
        input_paths=resolved_inputs,
        work_dir=work_dir,
        pdf_dpi=options.pdf_dpi,
    )

    page_results = []

    for page in pages:
        print(
            f"[Page {page.index + 1}"
            f"/{len(pages)}] "
            f"{page.image_path}"
        )

        page_output_dir = document_dir / page.id
        result = process_page(
            page=page,
            output_dir=page_output_dir,
            options=options,
        )

        page_results.append(result)

    manifest_path = (
        document_dir
        / "document.json"
    )

    doc_result = DocumentResult(
        source_path=primary_input,
        source_type=(
            primary_input.suffix
            .lower()
            .lstrip(".")
        ),
        output_dir=document_dir,
        pages=page_results,
        rebuilt_pptx_path=None,
    )

    with open(
        manifest_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            asdict(doc_result),
            file,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    if options.rebuild_pptx and len(page_results) > 0:
        pptx_output = options.rebuilt_pptx_path or (
            document_dir / f"{document_name}_rebuilt.pptx"
        )
        rebuilt_pptx_path = rebuild_pptx_from_document(
            document_json_path=manifest_path,
            output_pptx_path=pptx_output,
        )
        doc_result = DocumentResult(
            source_path=primary_input,
            source_type=(
                primary_input.suffix
                .lower()
                .lstrip(".")
            ),
            output_dir=document_dir,
            pages=page_results,
            rebuilt_pptx_path=rebuilt_pptx_path,
        )
        with open(
            manifest_path,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                asdict(doc_result),
                file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

    return doc_result