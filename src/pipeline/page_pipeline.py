import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

try:
    from src.inpainting.classical_inpainting import run_classical_inpainting_baseline
    from src.models.document import PageImage, PageResult, PipelineOptions
    from src.text_layer_extractor import ExtractionOptions, extract_text_layers
    from src.text_object_grouper import (
        build_text_objects,
        compose_text_object_layers,
        render_grouped_objects_preview,
    )
except ModuleNotFoundError:
    from inpainting.classical_inpainting import run_classical_inpainting_baseline
    from models.document import PageImage, PageResult, PipelineOptions
    from text_layer_extractor import ExtractionOptions, extract_text_layers
    from text_object_grouper import (
        build_text_objects,
        compose_text_object_layers,
        render_grouped_objects_preview,
    )


def process_page(
    page: PageImage,
    output_dir: Path,
    options: PipelineOptions,
    json_path: Optional[Path] = None,
) -> PageResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    ocr_json_path = json_path or run_paddleocr(page.image_path, output_dir / "ocr", options.ocr_lang)

    extraction_output = extract_text_layers(
        ExtractionOptions(
            image_path=page.image_path,
            json_path=ocr_json_path,
            output_dir=output_dir,
            min_score=options.min_score,
            padding=options.padding,
            debug_outputs=options.debug_outputs,
        )
    )

    objects = build_text_objects(extraction_output["layers"])
    objects = compose_text_object_layers(
        output_dir,
        extraction_output["layers"],
        objects,
    )
    objects_json = {
        "source_image": extraction_output["source_image"],
        "source_layers_json": str(output_dir / "layers.json"),
        "canvas": extraction_output["canvas"],
        "object_count": len(objects),
        "objects": objects,
    }

    objects_json_path = output_dir / "objects.json"
    with open(objects_json_path, "w", encoding="utf-8") as file:
        json.dump(objects_json, file, ensure_ascii=False, indent=2)

    if options.debug_outputs:
        preview = render_grouped_objects_preview(
            output_dir,
            extraction_output["layers"],
            objects,
            (
                extraction_output["canvas"]["height"],
                extraction_output["canvas"]["width"],
            ),
        )
        import cv2

        cv2.imwrite(str(output_dir / "grouped_objects_preview.png"), preview)

    background_path = None
    # if options.inpaint_backend == "telea":
    #     run_classical_inpainting_baseline(
    #         page.image_path,
    #         output_dir,
    #         extraction_output["layers"],
    #         dilate_kernel_size=options.dilate_kernel_size,
    #         inpaint_radius=options.inpaint_radius,
    #     )
    #     background_path = output_dir / "background_telea.png"
    # elif options.inpaint_backend != "none":
    #     raise ValueError(f"Unsupported inpaint backend: {options.inpaint_backend}")
    try:
        from src.inpainting.background_inpainter import (
            inpaint_background,
        )
    except ModuleNotFoundError:
        from inpainting.background_inpainter import (
            inpaint_background,
        )
    background_path = inpaint_background(
        image_path=page.image_path,
        output_dir=output_dir,
        layers=extraction_output["layers"],
        objects=objects,
        backend=options.inpaint_backend,
        dilate_kernel_size=options.dilate_kernel_size,
        inpaint_radius=options.inpaint_radius,
        harmonize=options.harmonize,
    )

    shutil.make_archive(str(output_dir), "zip", root_dir=output_dir)

    return PageResult(
        page=page,
        output_dir=output_dir,
        layers_json=output_dir / "layers.json",
        objects_json=objects_json_path,
        background_path=background_path,
    )


def run_paddleocr(image_path: Path, output_dir: Path, lang: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(build_paddleocr_command(image_path, output_dir, lang), check=True)

    expected = output_dir / f"{image_path.stem}_res.json"
    if expected.exists():
        return expected

    matches = sorted(output_dir.glob("*_res.json"))
    if matches:
        return matches[0]

    raise RuntimeError(f"PaddleOCR did not create result JSON in: {output_dir}")


def build_paddleocr_command(image_path: Path, output_dir: Path, lang: str) -> list[str]:
    local_model_root = Path.home() / ".paddlex" / "official_models"
    local_det_model_dir = local_model_root / "PP-OCRv5_mobile_det"
    local_rec_model_dir = local_model_root / "PP-OCRv5_mobile_rec"

    base_command = [
        "paddleocr",
        "ocr",
        "-i",
        str(image_path),
        "--lang",
        lang,
        "--text_detection_model_name",
        "PP-OCRv5_mobile_det",
        "--text_recognition_model_name",
        "PP-OCRv5_mobile_rec",
        "--use_doc_orientation_classify",
        "False",
        "--use_doc_unwarping",
        "False",
        "--use_textline_orientation",
        "False",
        "--save_path",
        str(output_dir),
    ]

    if local_det_model_dir.exists() and local_rec_model_dir.exists():
        base_command.extend(
            [
                "--text_detection_model_dir",
                str(local_det_model_dir),
                "--text_recognition_model_dir",
                str(local_rec_model_dir),
            ]
        )

    paddleocr_path = shutil.which("paddleocr")
    if paddleocr_path is not None:
        base_command[0] = paddleocr_path
        return base_command

    conda_exe = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if conda_exe is None:
        raise RuntimeError(
            "PaddleOCR command not found. Activate padocr or make conda available."
        )

    return [
        conda_exe,
        "run",
        "--no-capture-output",
        "-n",
        "padocr",
        *base_command,
    ]
