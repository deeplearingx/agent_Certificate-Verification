import argparse
import time
from pathlib import Path

from langchain_app.core import PipelineHooks, run_verification
from langchain_app.utils import get_app_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the document verification pipeline.")
    parser.add_argument("pdf", help="Path to the PDF file to verify.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_total = time.time()

    config = get_app_config()
    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    hooks = PipelineHooks(
        set_status=print,
        set_progress=lambda value: print(f"Progress: {value}%"),
        info=print,
        warning=lambda message: print(f"WARNING: {message}"),
        error=lambda message: print(f"ERROR: {message}"),
        success=lambda message: print(f"OK: {message}"),
    )

    report = run_verification(pdf_file_path=pdf_path, config=config, hooks=hooks)
    if not report:
        raise RuntimeError("Verification failed without producing a report.")

    output_path = config.final_reports_dir / f"Report_{pdf_path.stem}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Report saved to: {output_path}")
    print(f"Finished in {time.time() - start_total:.1f}s")


if __name__ == "__main__":
    main()
