import argparse
from pathlib import Path

try:
    from src.models.document import PipelineOptions
    from src.pipeline.document_pipeline import process_document
except ModuleNotFoundError:
    from models.document import PipelineOptions
    from pipeline.document_pipeline import process_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", default="output_document")
    parser.add_argument("-ms", "--min-score", type=float, default=0.50)
    parser.add_argument("-pd", "--padding", type=int, default=8)
    parser.add_argument("-dk", "--dilate-kernel", type=int, default=5)
    parser.add_argument("-ir", "--inpaint-radius", type=int, default=5)
    parser.add_argument("--pdf-dpi", type=int, default=200)
    parser.add_argument("--pptx-output", type=Path)
    parser.add_argument(
        "-nrb", "--no-rebuild-pptx",
        action="store_true",
        help="Disable rebuilt PPTX output",
    )
    parser.add_argument(
        "-ib", "--inpaint-backend",
        # choices=["telea", "none"],
        choices=[
            "none",
            "telea",
            "sd",
        ],
        default="telea",
    )
    parser.add_argument(
        "-nd",
        "--no-debug",
        action="store_true",
        help="Disable debug preview outputs",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = process_document(
        args.inputs,
        Path(args.output),
        PipelineOptions(
            min_score=args.min_score,
            padding=args.padding,
            debug_outputs=not args.no_debug,
            dilate_kernel_size=args.dilate_kernel,
            inpaint_radius=args.inpaint_radius,
            inpaint_backend=args.inpaint_backend,
            pdf_dpi=args.pdf_dpi,
            rebuild_pptx=not args.no_rebuild_pptx,
            rebuilt_pptx_path=args.pptx_output,
        ),
    )
    print(f"Done: {len(result.pages)} pages")
    print(f"Output: {result.output_dir}")
    if result.rebuilt_pptx_path is not None:
        print(f"PPTX: {result.rebuilt_pptx_path}")


if __name__ == "__main__":
    main()
