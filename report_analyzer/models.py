"""Structured schema for an analyzed fenestration test report.

A report has report-level identity fields plus one or more test *specimens*.
Performance ratings and frame/glazing/hardware construction are recorded
per specimen, because a single report often covers several configurations
(e.g. a "New Construction Frame" and a "Replacement Frame").
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class FrameMember:
    member: str
    material: str = ""
    detail: str = ""


@dataclass
class Glazing:
    glass_type: str = ""
    overall_thickness: str = ""
    makeup: str = ""
    method: str = ""
    bite: str = ""
    daylight_opening: str = ""


@dataclass
class HardwareItem:
    description: str
    quantity: str = ""
    location: str = ""


@dataclass
class Construction:
    """Frame / glazing / hardware detail for one specimen.

    ``raw_text`` preserves the cleaned source text of each section so that
    nothing is silently dropped when structured parsing is imperfect.
    """

    frame: List[FrameMember] = field(default_factory=list)
    glazing: Optional[Glazing] = None
    hardware: List[HardwareItem] = field(default_factory=list)
    raw_text: Dict[str, str] = field(default_factory=dict)


@dataclass
class Specimen:
    """One tested configuration within a report."""

    specimen_id: str = ""           # e.g. "1"
    label: str = ""                 # e.g. "New Construction Frame"
    model: str = ""                 # e.g. "830-PD"
    product_designator: str = ""    # e.g. "Class R - PG50 1829 x 2032 (72 x 80)-SD"
    design_pressure: str = ""       # e.g. "+70 / -70 psf" or "+/-2400 Pa (+/-50.13 psf)"
    air_infiltration: str = ""
    air_exfiltration: str = ""
    water_penetration: str = ""     # test pressure and/or result
    overall_size: str = ""          # e.g. "216 in x 120 in"
    area: str = ""                  # e.g. "180 ft2"
    leaf_size: str = ""             # operable leaf / panel size, if reported
    daylight_opening: str = ""      # glass daylight opening size(s)
    results: Dict[str, str] = field(default_factory=dict)  # test name -> pass/fail/value
    construction: Construction = field(default_factory=Construction)


@dataclass
class Report:
    """Top-level analyzed report."""

    source_file: str = ""
    report_number: str = ""
    revision: str = ""
    standard_family: str = ""       # human label, e.g. "TAS / Florida Building Code"
    test_standards: List[str] = field(default_factory=list)
    laboratory: str = ""
    laboratory_location: str = ""
    client: str = ""
    client_location: str = ""
    product_type: str = ""
    series_model: str = ""
    report_date: str = ""
    issue_date: str = ""
    revised_date: str = ""
    test_dates: str = ""
    test_completion_date: str = ""
    overall_result: str = ""
    specimens: List[Specimen] = field(default_factory=list)
    revisions: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Plain nested dict, dropping empty optionals for a tidy JSON."""
        return _prune(asdict(self))

    def flatten(self) -> List[dict]:
        """One flat row per specimen for CSV export.

        A report with no parsed specimens still yields a single row so it is
        never invisible in the summary.
        """
        base = {
            "source_file": self.source_file,
            "report_number": self.report_number,
            "revision": self.revision,
            "standard_family": self.standard_family,
            "test_standards": "; ".join(self.test_standards),
            "laboratory": self.laboratory,
            "client": self.client,
            "client_location": self.client_location,
            "product_type": self.product_type,
            "series_model": self.series_model,
            "report_date": self.report_date,
            "issue_date": self.issue_date,
            "revised_date": self.revised_date,
            "test_dates": self.test_dates,
            "test_completion_date": self.test_completion_date,
            "overall_result": self.overall_result,
        }
        specimens = self.specimens or [Specimen()]
        rows = []
        for spec in specimens:
            row = dict(base)
            row.update(
                {
                    "specimen_id": spec.specimen_id,
                    "specimen_label": spec.label,
                    "specimen_model": spec.model,
                    "product_designator": spec.product_designator,
                    "design_pressure": spec.design_pressure,
                    "air_infiltration": spec.air_infiltration,
                    "air_exfiltration": spec.air_exfiltration,
                    "water_penetration": spec.water_penetration,
                    "overall_size": spec.overall_size,
                    "area": spec.area,
                    "leaf_size": spec.leaf_size,
                    "daylight_opening": spec.daylight_opening,
                    "frame": _frame_summary(spec.construction.frame),
                    "glazing": _glazing_summary(spec.construction.glazing),
                    "hardware": _hardware_summary(spec.construction.hardware),
                    "test_results": "; ".join(
                        f"{k}: {v}" for k, v in spec.results.items()
                    ),
                }
            )
            rows.append(row)
        return rows


CSV_COLUMNS = [
    "source_file", "report_number", "revision", "standard_family", "test_standards",
    "laboratory", "client", "client_location", "product_type", "series_model",
    "report_date", "issue_date", "revised_date", "test_dates", "test_completion_date",
    "overall_result", "specimen_id", "specimen_label", "specimen_model",
    "product_designator", "design_pressure", "air_infiltration", "air_exfiltration",
    "water_penetration", "overall_size", "area", "leaf_size", "daylight_opening",
    "frame", "glazing", "hardware", "test_results",
]


def _frame_summary(frame: List[FrameMember]) -> str:
    return " | ".join(
        " - ".join(p for p in (m.member, m.material, m.detail) if p) for m in frame
    )


def _glazing_summary(glazing: Optional[Glazing]) -> str:
    if not glazing:
        return ""
    parts = [
        glazing.glass_type,
        glazing.overall_thickness,
        glazing.makeup,
        f"bite {glazing.bite}" if glazing.bite else "",
    ]
    return "; ".join(p for p in parts if p)


def _hardware_summary(hardware: List[HardwareItem]) -> str:
    return " | ".join(
        " - ".join(p for p in (h.quantity, h.description, h.location) if p)
        for h in hardware
    )


def _prune(value):
    """Recursively drop empty strings/lists/dicts/None for compact JSON."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            pruned = _prune(v)
            if pruned not in (None, "", [], {}):
                out[k] = pruned
        return out
    if isinstance(value, list):
        return [_prune(v) for v in value if _prune(v) not in (None, "", [], {})]
    return value
