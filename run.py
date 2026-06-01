#!/usr/bin/env python3
"""Cross-platform launcher for the test report analyzer.

Pure Python (no .bat), so downloads of this project are not flagged by
antivirus/SmartScreen the way batch files are.

Usage::

    python run.py                      # analyze the ./reports folder
    python run.py path/to/folder       # analyze a folder of PDFs
    python run.py a.pdf b.pdf          # analyze specific PDFs

It installs dependencies on first run, writes ``output/TR_Summary.xlsx`` and
``output/summary.csv``, and opens the output folder on desktop systems.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _ensure_deps() -> None:
    try:
        import fitz  # noqa: F401  (PyMuPDF)
        import openpyxl  # noqa: F401
        return
    except ImportError:
        print("Installing dependencies (one-time, needs internet)...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r",
             os.path.join(HERE, "requirements.txt")]
        )


def _open_folder(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass  # headless (e.g. a Codespace) - the path is printed below


def main() -> int:
    os.chdir(HERE)
    _ensure_deps()

    targets = sys.argv[1:]
    if not targets:
        os.makedirs("reports", exist_ok=True)
        targets = ["reports"]
        print(f'No folder given; using the "reports" folder: {os.path.join(HERE, "reports")}')

    os.makedirs("output", exist_ok=True)
    cmd = [
        sys.executable, "-m", "report_analyzer", *targets,
        "--xlsx", "output/TR_Summary.xlsx",
        "--csv", "output/summary.csv",
        "--print",
    ]
    result = subprocess.run(cmd)
    if result.returncode == 0:
        out = os.path.join(HERE, "output")
        print(f"\nDone. Your summary is in: {out}")
        print("  - TR_Summary.xlsx  (FX/SD summary, one row per specimen)")
        print("  - summary.csv")
        _open_folder(out)
    else:
        print("\nSomething went wrong - see the messages above.")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
