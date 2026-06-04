"""AI-powered extraction backend (Claude API).

Reads *any* fenestration test report into the same ``Report`` / ``Specimen``
structures the rules-based parser produces, so the JSON / CSV / XLSX exporters
work unchanged. Because Claude reads the report directly, this handles
arbitrary laboratory formats with no per-lab code.

A single structured-output call per report (``claude-opus-4-8`` by default),
with the long instruction block cached so batch runs are cheap. Requires the
``anthropic`` package and an ``ANTHROPIC_API_KEY`` (or other SDK-resolved
credential).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .extraction import load_document
from .models import Construction, FrameMember, Glazing, HardwareItem, Report, Specimen

DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
You are an expert at reading window and door (fenestration) building-code test \
reports and extracting structured product information.

You receive the full text of one test report from any laboratory and in any \
format (e.g. TAS / Florida Building Code; AAMA/WDMA/CSA 101 I.S.2/A440 "NAFS"; \
others). Extract the fields defined by the output schema. A single report may \
cover several tested configurations (called specimens, products, or series) - \
return one entry in `specimens` for each distinct configuration.

Rules:
- Copy values from the report; never invent data. If a field is absent, return \
an empty string "" (or an empty array). Do not guess.
- report_date / revised_date: format as MM/DD/YYYY when a date is given. If the \
report was revised, put the revised date in revised_date.
- design_pressure: the design pressure in psf, e.g. "+50 / -50 psf". If only Pa \
is given, use the psf value shown (usually in parentheses).
- product_designator: the rating / primary designator string, e.g. \
"Class LC - PG50 ... - Type SLT" or "Class R - PG50 ...".
- overall_size / leaf_size: "WIDTH x HEIGHT in" using the inch values \
(e.g. "96 x 144 in"). leaf_size is the operable panel/leaf size if reported.
- daylight_opening: the glass daylight-opening size(s).
- glazing.makeup: the glass build-up from EXTERIOR to INTERIOR, one layer per \
line (use newlines between layers).
- frame: the frame members with material and a short detail each. If the \
construction is written as prose, summarise each member as one entry.
- hardware: hardware items with quantity and location; if "None", return [].
- results: one name/value pair per test performed (air infiltration/exfiltration, \
water penetration, uniform load / structural, forced entry, impact, deglazing, \
corner weld, etc.) with the pass/fail or measured value.
- product_category: "door" if the product is a door / sliding / patio / slider; \
otherwise "window" (sidelites, transoms, mullion assemblies, and fixed or \
operable windows are all "window").
- standard_family: a short label such as \
"AAMA/WDMA/CSA 101/I.S.2/A440 (NAFS)" or "TAS / Florida Building Code".
- overall_result: a short pass/fail summary if the report states one.

Return only information that is present in the report."""


def _obj(props: dict, required=None) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_FRAME_ITEM = _obj({"member": _STR, "material": _STR, "detail": _STR})
_HW_ITEM = _obj({"description": _STR, "quantity": _STR, "location": _STR})
_RESULT_ITEM = _obj({"name": _STR, "value": _STR})
_GLAZING = _obj({
    "glass_type": _STR, "overall_thickness": _STR, "makeup": _STR,
    "method": _STR, "bite": _STR, "daylight_opening": _STR,
})
_SPECIMEN = _obj({
    "specimen_id": _STR, "label": _STR, "model": _STR,
    "product_designator": _STR, "design_pressure": _STR,
    "air_infiltration": _STR, "air_exfiltration": _STR, "water_penetration": _STR,
    "overall_size": _STR, "leaf_size": _STR, "daylight_opening": _STR,
    "frame": {"type": "array", "items": _FRAME_ITEM},
    "glazing": _GLAZING,
    "hardware": {"type": "array", "items": _HW_ITEM},
    "results": {"type": "array", "items": _RESULT_ITEM},
})
SCHEMA = _obj({
    "report_number": _STR, "revision": _STR, "standard_family": _STR,
    "test_standards": {"type": "array", "items": _STR},
    "laboratory": _STR, "client": _STR,
    "product_type": _STR, "series_model": _STR,
    "product_category": {"type": "string", "enum": ["window", "door", ""]},
    "report_date": _STR, "revised_date": _STR, "test_dates": _STR,
    "overall_result": _STR,
    "specimens": {"type": "array", "items": _SPECIMEN},
})


def _to_report(data: dict, source: str) -> Report:
    """Map the model's JSON output into a :class:`Report`."""
    report = Report(
        source_file=source,
        report_number=data.get("report_number", ""),
        revision=data.get("revision", ""),
        standard_family=data.get("standard_family", ""),
        test_standards=list(data.get("test_standards") or []),
        laboratory=data.get("laboratory", ""),
        client=data.get("client", ""),
        product_type=data.get("product_type", ""),
        series_model=data.get("series_model", ""),
        product_category=data.get("product_category", ""),
        report_date=data.get("report_date", ""),
        revised_date=data.get("revised_date", ""),
        test_dates=data.get("test_dates", ""),
        overall_result=data.get("overall_result", ""),
    )
    for s in data.get("specimens") or []:
        spec = Specimen(
            specimen_id=str(s.get("specimen_id", "")),
            label=s.get("label", ""),
            model=s.get("model", ""),
            product_designator=s.get("product_designator", ""),
            design_pressure=s.get("design_pressure", ""),
            air_infiltration=s.get("air_infiltration", ""),
            air_exfiltration=s.get("air_exfiltration", ""),
            water_penetration=s.get("water_penetration", ""),
            overall_size=s.get("overall_size", ""),
            leaf_size=s.get("leaf_size", ""),
            daylight_opening=s.get("daylight_opening", ""),
        )
        con = Construction()
        g = s.get("glazing") or {}
        if any(g.values()):
            con.glazing = Glazing(
                glass_type=g.get("glass_type", ""),
                overall_thickness=g.get("overall_thickness", ""),
                makeup=g.get("makeup", ""),
                method=g.get("method", ""),
                bite=g.get("bite", ""),
                daylight_opening=g.get("daylight_opening", ""),
            )
        con.frame = [
            FrameMember(member=f.get("member", ""), material=f.get("material", ""),
                        detail=f.get("detail", ""))
            for f in (s.get("frame") or [])
        ]
        con.hardware = [
            HardwareItem(description=h.get("description", ""), quantity=h.get("quantity", ""),
                         location=h.get("location", ""))
            for h in (s.get("hardware") or [])
        ]
        spec.construction = con
        spec.results = {
            item.get("name", ""): item.get("value", "")
            for item in (s.get("results") or []) if item.get("name")
        }
        report.specimens.append(spec)
    return report


def _parse_json(resp) -> dict:
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if getattr(resp, "stop_reason", "") == "refusal":
        raise RuntimeError("The model refused to extract this report.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if getattr(resp, "stop_reason", "") == "max_tokens":
            raise RuntimeError(
                "Extraction was truncated (hit max_tokens). Re-run with a larger "
                "--max-tokens for very large reports."
            ) from exc
        raise RuntimeError(f"Model did not return valid JSON: {exc}") from exc


def analyze_text_ai(
    text: str,
    source: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 16000,
    client=None,
) -> Report:
    """Extract a :class:`Report` from raw report text via the Claude API."""
    if client is None:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise RuntimeError(
                "AI extraction needs an API key. Set ANTHROPIC_API_KEY in your "
                "environment (get one at https://console.anthropic.com), then re-run."
            )
        import anthropic  # imported lazily so rules mode never requires it

        client = anthropic.Anthropic()

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        output_config={
            "format": {"type": "json_schema", "schema": SCHEMA},
            "effort": "medium",
        },
        messages=[{"role": "user", "content": f"Test report text:\n\n{text}"}],
    )
    return _to_report(_parse_json(resp), source)


def analyze_pdf_ai(
    path: str,
    model: str = DEFAULT_MODEL,
    password: str = "",
    max_tokens: int = 16000,
    client=None,
) -> Report:
    """Load a PDF and extract it with the Claude API."""
    doc = load_document(path, password=password)
    report = analyze_text_ai(doc.full_text, source=path, model=model,
                             max_tokens=max_tokens, client=client)
    report.source_file = path
    return report
