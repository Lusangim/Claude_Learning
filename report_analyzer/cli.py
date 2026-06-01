"""Command-line interface for the fenestration test-report analyzer.

Examples
--------
Analyze two PDFs, print summaries, and write JSON + CSV::

    python -m report_analyzer reportA.pdf reportB.pdf \\
        --json-dir output --csv output/summary.csv --print

Scan every PDF in a folder::

    python -m report_analyzer ./reports/*.pdf --json-dir output --csv output/summary.csv
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

from .export import default_json_name, summarize, write_csv, write_json
from .models import Report
from .parsing import analyze_pdf


def _use_ai(mode: str) -> bool:
    """Decide whether to use the AI backend for the given --mode."""
    if mode == "ai":
        return True
    if mode == "rules":
        return False
    # auto: use AI when a key is available, else fall back to rules.
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _analyze_one(path: str, mode: str, model: str, password: str) -> Report:
    if _use_ai(mode):
        from .ai_extract import analyze_pdf_ai

        return analyze_pdf_ai(path, model=model, password=password)
    return analyze_pdf(path, password=password)


def _gather_pdfs(inputs: List[str]) -> List[str]:
    pdfs: List[str] = []
    for item in inputs:
        if os.path.isdir(item):
            for name in sorted(os.listdir(item)):
                if name.lower().endswith(".pdf"):
                    pdfs.append(os.path.join(item, name))
        else:
            pdfs.append(item)
    return pdfs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="report_analyzer",
        description="Extract product information from fenestration (window/door) "
        "building-code test report PDFs.",
    )
    p.add_argument("pdfs", nargs="+", help="PDF files or directories to analyze")
    p.add_argument("--json-dir", metavar="DIR", help="write one JSON per report into DIR")
    p.add_argument("--csv", metavar="FILE", help="write a flat one-row-per-specimen summary CSV")
    p.add_argument(
        "--xlsx", metavar="FILE",
        help="write an Excel summary in the FX/SD 'TR Summary' template layout",
    )
    p.add_argument(
        "--xlsx-template", metavar="SRC",
        help="with --xlsx, append rows into a copy of this template workbook "
        "instead of building a fresh one",
    )
    p.add_argument("--password", default="", help="password for encrypted PDFs (default: empty)")
    p.add_argument(
        "--mode", choices=["auto", "ai", "rules"], default="auto",
        help="extraction backend: 'ai' (Claude, handles any format; needs "
        "ANTHROPIC_API_KEY), 'rules' (built-in TAS/NAFS parser, no API), or "
        "'auto' (AI if a key is set, else rules). Default: auto.",
    )
    p.add_argument("--ai", action="store_true", help="shortcut for --mode ai")
    p.add_argument("--rules", action="store_true", help="shortcut for --mode rules")
    p.add_argument(
        "--model", default="claude-opus-4-8",
        help="Claude model for --mode ai (default: claude-opus-4-8)",
    )
    p.add_argument("--print", dest="show", action="store_true", help="print a summary per report")
    p.add_argument("--quiet", action="store_true", help="suppress progress messages")
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pdfs = _gather_pdfs(args.pdfs)
    if not pdfs:
        print("No PDF files found.", file=sys.stderr)
        return 2

    mode = "ai" if args.ai else "rules" if args.rules else args.mode
    if not args.quiet:
        backend = "AI (Claude)" if _use_ai(mode) else "rules"
        print(f"[backend] {backend}", file=sys.stderr)

    reports: List[Report] = []
    failures = 0
    for path in pdfs:
        try:
            report = _analyze_one(path, mode, args.model, args.password)
        except Exception as exc:  # keep going across a batch
            failures += 1
            print(f"[error] {path}: {exc}", file=sys.stderr)
            continue
        reports.append(report)
        if not args.quiet:
            print(f"[ok] {path} -> {report.report_number or '(no report number)'}", file=sys.stderr)
        if args.show:
            print("\n" + summarize(report) + "\n")
        if args.json_dir:
            out = os.path.join(args.json_dir, default_json_name(report))
            write_json(report, out)
            if not args.quiet:
                print(f"      json: {out}", file=sys.stderr)

    if args.csv and reports:
        n = write_csv(reports, args.csv)
        if not args.quiet:
            print(f"[csv] {n} specimen row(s) -> {args.csv}", file=sys.stderr)

    if args.xlsx and reports:
        os.makedirs(os.path.dirname(os.path.abspath(args.xlsx)), exist_ok=True)
        try:
            from .xlsx_export import fill_template, write_xlsx
        except ImportError:
            print("[error] --xlsx requires openpyxl (pip install openpyxl)", file=sys.stderr)
            return 3
        if args.xlsx_template:
            fx, sd = fill_template(reports, args.xlsx_template, args.xlsx)
            origin = f"filled from {args.xlsx_template}"
        else:
            fx, sd = write_xlsx(reports, args.xlsx)
            origin = "new workbook"
        if not args.quiet:
            print(f"[xlsx] {fx} FX + {sd} SD row(s) ({origin}) -> {args.xlsx}", file=sys.stderr)

    if not reports:
        return 1
    return 0 if failures == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
