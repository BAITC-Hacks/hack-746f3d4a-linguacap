#!/usr/bin/env python3
"""Compare saved local ASR results with locally supplied DOCX references.

Usage intentionally writes detailed error excerpts only beneath the ignored
``services/asr/runtime`` directory.  The Markdown report is safe to version:
it contains metrics and category counts, not transcript text.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.quality import compare_actions, compare_tokens, reference_from_docx, sanitized_markdown_report  # noqa: E402
from app.storage import LocalProtocolStore  # noqa: E402


def parse_case(value: str) -> tuple[str, str, Path]:
    try:
        label, job_id, reference = value.split("::", 2)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Формат --case: Название::job-id::/путь/к/эталону.docx") from error
    if not label.strip() or not job_id.strip() or not reference.strip():
        raise argparse.ArgumentTypeError("В --case должны быть заполнены название, job-id и путь к DOCX.")
    return label.strip(), job_id.strip(), Path(reference).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальное сравнение транскриптов с эталонными DOCX.")
    parser.add_argument("--store", type=Path, default=SERVICE_ROOT / "runtime" / "protocols.sqlite3")
    parser.add_argument("--case", action="append", type=parse_case, required=True)
    parser.add_argument("--public-report", type=Path, required=True)
    parser.add_argument("--private-report", type=Path, required=True)
    args = parser.parse_args()

    store = LocalProtocolStore(args.store)
    comparisons: list[dict[str, object]] = []
    for label, job_id, reference_path in args.case:
        if not reference_path.is_file():
            parser.error(f"Не найден эталонный DOCX: {reference_path}")
        result = store.result_for(job_id)
        if result is None:
            parser.error(f"Не найден сохранённый результат для задания {job_id[:8]}…")
        analysis = store.analysis_for(job_id) or {}
        reference_paragraphs, reference_actions = reference_from_docx(reference_path)
        transcript = compare_tokens("\n".join(reference_paragraphs), result.get("segments", []))
        protocol_actions = [str(item.get("description", "")) for item in analysis.get("action_items", []) if isinstance(item, dict)]
        actions = compare_actions(reference_actions, protocol_actions)
        comparisons.append({"label": label, "transcript": transcript, "actions": actions})

    generated_on = date.today().isoformat()
    args.public_report.parent.mkdir(parents=True, exist_ok=True)
    args.private_report.parent.mkdir(parents=True, exist_ok=True)
    args.public_report.write_text(sanitized_markdown_report(comparisons, generated_on), encoding="utf-8")
    args.private_report.write_text(json.dumps({"generated_on": generated_on, "comparisons": comparisons}, ensure_ascii=False, indent=2), encoding="utf-8")

    safe_summary = [
        {
            "recording": comparison["label"],
            "exact_token_coverage": comparison["transcript"]["exact_token_coverage"],
            "error_units": comparison["transcript"]["error_units"],
            "matched_actions": comparison["actions"]["matched_actions"],
        }
        for comparison in comparisons
    ]
    print(json.dumps({"report": str(args.public_report), "results": safe_summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
