"""Fenestration test-report analyzer.

Scans window/door building-code test report PDFs (e.g. Intertek/TAS Florida
Building Code reports and AAMA/WDMA/CSA 101 NAFS reports) and extracts
structured product information: identity, performance ratings, and the
frame / glazing / hardware construction of each test specimen.

Typical use::

    from report_analyzer import analyze_pdf
    report = analyze_pdf("path/to/report.pdf")
    print(report.report_number, report.overall_result)

Or from the command line::

    python -m report_analyzer report1.pdf report2.pdf --json-dir output --csv output/summary.csv
"""

from .extraction import load_document
from .models import Report, Specimen
from .parsing import analyze, analyze_pdf


def analyze_pdf_ai(*args, **kwargs):
    """AI-powered extraction (lazy import so rules mode never requires anthropic)."""
    from .ai_extract import analyze_pdf_ai as _impl

    return _impl(*args, **kwargs)


__all__ = ["analyze", "analyze_pdf", "analyze_pdf_ai", "load_document", "Report", "Specimen"]
__version__ = "0.1.0"
