import argparse
import json
import shutil
from pathlib import Path

try:
    from src.inpainting.classical_inpainting import run_classical_inpainting_baseline
    from src.text_layer_extractor import ExtractionOptions, extract_text_layers
    from src.text_object_grouper import (
        build_text_objects,
        compose_text_object_layers,
        render_grouped_objects_preview,
    )
except ModuleNotFoundError:
    from inpainting.classical_inpainting import run_classical_inpainting_baseline
    from text_layer_extractor import ExtractionOptions, extract_text_layers
    from text_object_grouper import (
        build_text_objects,
        compose_text_object_layers,
        render_grouped_objects_preview,
    )
try:
    from src.document_cli import main as document_main
except ModuleNotFoundError:
    from document_cli import main as document_main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("-i", "--image", help="Original slide image")
    parser.add_argument("-j", "--json", help="PaddleOCR result JSON")
    parser.add_argument("-o", "--output", default="output_layers")
    parser.add_argument("-ms", "--min-score", type=float, default=0.50)
    parser.add_argument(
        "-dk", "--dilate-kernel",
        type=int,
        default=3,
    )
    parser.add_argument(
        "-ir", "--inpaint-radius",
        type=int,
        default=1,
        help="OpenCV inpainting neighborhood radius",
    )
    parser.add_argument("-pdi", "--pdf-dpi", type=int, default=120)
    parser.add_argument("-ppto", "--pptx-output", type=Path)
    parser.add_argument(
        "-nbppt",
        "--no-rebuild-pptx",
        action="store_true",
        help="Disable rebuilt PPTX output for document inputs",
    )
    parser.add_argument(
        "-ib", 
        "--inpaint-backend",
        choices=["telea", "none"],
        default="telea",
    )
    parser.add_argument("-pd", "--padding", type=int, default=8)
    parser.add_argument(
        "-nd", "--no-debug",
        action="store_true",
        help="Disable debug preview outputs",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.inputs:
        if args.image or args.json:
            parser.error("Use either positional document inputs or --image/--json, not both.")
        document_main()
        return
    if not args.image or not args.json:
        parser.error("--image and --json are required when no positional input is provided.")

    extraction_output = extract_text_layers(
        ExtractionOptions(
            image_path=Path(args.image),
            json_path=Path(args.json),
            output_dir=Path(args.output),
            min_score=args.min_score,
            padding=args.padding,
            debug_outputs=not args.no_debug,
        )
    )

    objects = build_text_objects(extraction_output["layers"])
    objects = compose_text_object_layers(
        Path(args.output),
        extraction_output["layers"],
        objects,
    )
    objects_json = {
        "source_image": extraction_output["source_image"],
        "source_layers_json": str(Path(args.output) / "layers.json"),
        "canvas": extraction_output["canvas"],
        "object_count": len(objects),
        "objects": objects,
    }

    output_dir = Path(args.output)
    with open(output_dir / "objects.json", "w", encoding="utf-8") as file:
        json.dump(objects_json, file, ensure_ascii=False, indent=2)

    if not args.no_debug:
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

    if args.inpaint_backend == "telea":
        run_classical_inpainting_baseline(
            Path(args.image),
            output_dir,
            extraction_output["layers"],
            dilate_kernel_size=args.dilate_kernel,
            inpaint_radius=args.inpaint_radius,
        )
    elif args.inpaint_backend != "none":
        parser.error(f"Unsupported inpaint backend: {args.inpaint_backend}")

    shutil.make_archive(str(output_dir), "zip", root_dir=output_dir)


if __name__ == "__main__":
    main()
