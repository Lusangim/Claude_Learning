"""Write analyzed reports to JSON (full detail) and CSV (flat summary)."""

from __future__ import annotations

import csv
import json
import os
from typing import Iterable, List

from .models import CSV_COLUMNS, Report


def report_to_json(report: Report, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent, ensure_ascii=False)


def write_json(report: Report, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report_to_json(report))


def write_csv(reports: Iterable[Report], path: str) -> int:
    """Write one row per specimen across all reports. Returns row count."""
    rows: List[dict] = []
    for report in reports:
        rows.extend(report.flatten())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def default_json_name(report: Report) -> str:
    """A filesystem-safe JSON filename derived from the report number/source."""
    stem = report.report_number or os.path.splitext(os.path.basename(report.source_file))[0]
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in stem)
    return f"{safe or 'report'}.json"


def summarize(report: Report) -> str:
    """Compact human-readable summary for terminal output."""
    lines = [
        f"Report:      {report.report_number}  ({report.standard_family})",
        f"Source:      {os.path.basename(report.source_file)}",
        f"Client:      {report.client}",
        f"Laboratory:  {report.laboratory}",
        f"Product:     {report.product_type}  |  {report.series_model}",
        f"Standards:   {', '.join(report.test_standards)}",
        f"Dates:       test={report.test_dates or '-'}  report={report.report_date or report.issue_date or '-'}",
        f"Result:      {report.overall_result or '(not stated)'}",
        f"Specimens:   {len(report.specimens)}",
    ]
    for spec in report.specimens:
        tag = f"#{spec.specimen_id}" + (f" {spec.label}" if spec.label else "")
        lines.append(f"  - {tag} {('['+spec.model+']') if spec.model else ''}".rstrip())
        if spec.product_designator:
            lines.append(f"      designator: {spec.product_designator}")
        if spec.design_pressure:
            lines.append(f"      design pressure: {spec.design_pressure}")
        if spec.overall_size:
            lines.append(f"      size: {spec.overall_size}  area: {spec.area}")
        if spec.air_infiltration:
            lines.append(f"      air infiltration: {spec.air_infiltration}")
        if spec.water_penetration:
            lines.append(f"      water penetration: {spec.water_penetration}")
        if spec.construction.frame:
            fr = "; ".join(f"{m.member}: {m.material}" for m in spec.construction.frame[:4])
            lines.append(f"      frame: {fr}")
        if spec.construction.glazing and spec.construction.glazing.glass_type:
            g = spec.construction.glazing
            lines.append(f"      glazing: {g.glass_type} {g.overall_thickness} (bite {g.bite})".rstrip())
        if spec.construction.hardware:
            hw = "; ".join(h.description for h in spec.construction.hardware[:4])
            lines.append(f"      hardware: {hw}")
        if spec.results:
            lines.append(f"      results: {', '.join(f'{k}={v}' for k, v in spec.results.items())}")
    if report.warnings:
        lines.append("  warnings: " + " | ".join(report.warnings))
    return "\n".join(lines)
