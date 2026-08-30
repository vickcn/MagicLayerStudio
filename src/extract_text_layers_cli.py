import argparse
import json
import shutil
from pathlib import Path

try:
    from src.classical_inpainting import run_classical_inpainting_baseline
    from src.text_layer_extractor import ExtractionOptions, extract_text_layers
    from src.text_object_grouper import (
        build_text_objects,
        compose_text_object_layers,
        render_grouped_objects_preview,
    )
except ModuleNotFoundError:
    from classical_inpainting import run_classical_inpainting_baseline
    from text_layer_extractor import ExtractionOptions, extract_text_layers
    from text_object_grouper import (
        build_text_objects,
        compose_text_object_layers,
        render_grouped_objects_preview,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--image", required=True, help="Original slide image")
    parser.add_argument("-j", "--json", required=True, help="PaddleOCR result JSON")
    parser.add_argument("-o", "--output", default="output_layers")
    parser.add_argument("-ms", "--min-score", type=float, default=0.50)
    parser.add_argument(
        "-dk", "--dilate-kernel",
        type=int,
        default=5,
    )
    parser.add_argument(
        "-ir", "--inpaint-radius",
        type=int,
        default=5,
        help="OpenCV inpainting neighborhood radius",
    )
    parser.add_argument("-pd", "--padding", type=int, default=8)
    parser.add_argument(
        "-nd", "--no-debug",
        action="store_true",
        help="Disable debug preview outputs",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
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

    # run_classical_inpainting_baseline(
    #     Path(args.image),
    #     output_dir,
    #     extraction_output["layers"],
    # )
    run_classical_inpainting_baseline(
        Path(args.image),
        output_dir,
        extraction_output["layers"],
        dilate_kernel_size=args.dilate_kernel,
        inpaint_radius=args.inpaint_radius,
    )

    shutil.make_archive(str(output_dir), "zip", root_dir=output_dir)


if __name__ == "__main__":
    main()
