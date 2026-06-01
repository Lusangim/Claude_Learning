"""Turn an extracted :class:`~report_analyzer.extraction.Document` into a
structured :class:`~report_analyzer.models.Report`.

Two report layouts are recognised explicitly, with a generic fallback:

* **TAS** - Intertek-style Florida Building Code reports (TAS 201/202/203),
  numbered "SECTION" headers, usually one specimen, tables without rules.
* **NAFS** - AAMA/WDMA/CSA 101/I.S.2/A440 reports, labelled headers, often
  several specimens, ruled tables.

The high-value identity and performance fields are pulled with anchored
regexes (very reliable). Frame / glazing / hardware are recovered from ruled
tables where available and from the text stream otherwise; in every case the
cleaned source text of each construction section is preserved under
``construction.raw_text`` so no information is silently lost.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .extraction import Document, Table, load_document
from .models import (
    Construction,
    FrameMember,
    Glazing,
    HardwareItem,
    Report,
    Specimen,
)

# --------------------------------------------------------------------------- #
# Small text helpers
# --------------------------------------------------------------------------- #

_UNICODE_FIXES = {
    "–": "-", "—": "-",        # en / em dash
    "‘": "'", "’": "'",        # smart single quotes
    "“": '"', "”": '"',        # smart double quotes
    " ": " ", " ": " ", " ": " ",  # non-breaking spaces
    "ﬁ": "fi", "ﬂ": "fl",
}


def clean(text: str) -> str:
    """Normalise unicode punctuation and collapse runs of whitespace."""
    if not text:
        return ""
    for bad, good in _UNICODE_FIXES.items():
        text = text.replace(bad, good)
    return " ".join(text.split()).strip(" :\t")


def _lines(text: str) -> List[str]:
    return [clean(ln) for ln in text.splitlines() if clean(ln)]


def labeled(text: str, label: str) -> str:
    """Value for ``label``, whether it sits on the same line or the next one.

    ``label`` is a regular-expression fragment (e.g. ``r"Report No\\.?"``).
    """
    same = re.search(label + r"\s*:?\s*(.+)", text, re.I)
    if same and clean(same.group(1)):
        return clean(same.group(1))
    nxt = re.search(label + r"\s*:?\s*\n\s*(.+)", text, re.I)
    if nxt:
        return clean(nxt.group(1))
    return ""


def labeled_longest(text: str, label: str) -> str:
    """Longest same-line value for ``label`` anywhere in the document.

    Fields like Series/Model appear both in a summary (where they wrap across
    two lines and read truncated) and in the specimen description (one full
    line). Taking the longest same-line match recovers the complete value.
    """
    best = ""
    for m in re.finditer(label + r"\s*:?\s*(.+)", text, re.I):
        val = clean(m.group(1))
        if len(val) > len(best):
            best = val
    return best or labeled(text, label)


def first(pattern: str, text: str, group: int = 1, flags=re.I) -> str:
    m = re.search(pattern, text, flags)
    return clean(m.group(group)) if m else ""


def section(text: str, start: str, ends: List[str]) -> str:
    """Substring from just after ``start`` up to the earliest of ``ends``."""
    sm = re.search(start, text, re.I)
    if not sm:
        return ""
    rest = text[sm.end():]
    cut = len(rest)
    for end in ends:
        em = re.search(end, rest, re.I)
        if em:
            cut = min(cut, em.start())
    return rest[:cut]


# --------------------------------------------------------------------------- #
# Format detection
# --------------------------------------------------------------------------- #

FAMILY_NAFS = "AAMA/WDMA/CSA 101/I.S.2/A440 (NAFS)"
FAMILY_TAS = "TAS / Florida Building Code"
FAMILY_GENERIC = "Unknown"


def detect_family(text: str) -> str:
    if re.search(r"AAMA/WDMA/CSA\s*101", text, re.I):
        return FAMILY_NAFS
    if re.search(r"\bTAS\s*20[123]\b", text, re.I) or re.search(
        r"Florida Building Code", text, re.I
    ):
        return FAMILY_TAS
    return FAMILY_GENERIC


# --------------------------------------------------------------------------- #
# Shared field extraction
# --------------------------------------------------------------------------- #

_REPORT_NO_RE = re.compile(r"\b([A-Z]{0,3}\d{3,}\.\d{2}-\d{3}-\d{2}(?:-R\d+)?)\b")


def _extract_identity(doc: Document, report: Report) -> None:
    text = doc.full_text
    head = doc.text_through_page(3)  # identity always lives on the first pages

    m = _REPORT_NO_RE.search(text)
    if m:
        report.report_number = m.group(1)
    if not report.report_number:
        report.report_number = labeled(head, r"Report No\.?")
    rev = re.search(r"-R(\d+)\b", report.report_number)
    if rev:
        report.revision = "R" + rev.group(1)

    report.product_type = labeled_longest(text, r"Product Type")
    report.series_model = labeled_longest(text, r"Series\s*/?\s*Model")

    report.test_standards = _extract_standards(text)
    report.report_date = first(r"Report Date:?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", text)
    report.revised_date = first(
        r"Revised Report Dated\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", text
    )
    report.issue_date = first(r"ISSUE DATE\s*\n\s*([0-9/.\- ]+)", text) or first(
        r"\bDate:\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", head
    )
    report.test_dates = first(r"TEST DATES\s*\n\s*([0-9/.\-– ]+)", text) or first(
        r"Test Dates:\s*([0-9/.\-– ]+(?:to|through|-|–)[0-9/.\-– ]+)", text
    )
    report.test_completion_date = first(
        r"Test Completion Date:?\s*\n?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})", text
    )


def _extract_standards(text: str) -> List[str]:
    found: List[str] = []
    for m in re.finditer(r"AAMA/WDMA/CSA\s*101/I\.S\.2/A440-\d{2}", text, re.I):
        s = clean(m.group(0))
        if s not in found:
            found.append(s)
    for m in re.finditer(r"\bTAS\s*20[123](?:-\d{2})?\b", text, re.I):
        s = re.sub(r"\s+", " ", clean(m.group(0)).upper().replace("TAS", "TAS "))
        if s not in found:
            found.append(s)
    # Drop a bare "TAS 201" when the versioned "TAS 201-94" is also present.
    versioned_bases = {s.split("-")[0] for s in found if re.search(r"TAS \d+-\d{2}", s)}
    found = [s for s in found if not (re.fullmatch(r"TAS \d+", s) and s in versioned_bases)]
    return found


def _size_after(text: str, label: str) -> str:
    """A 'WIDTH in x HEIGHT in' size from a size table row.

    The rows linearise as mm-width, in-width, mm-height, in-height; the
    imperial values are reported.
    """
    m = re.search(
        label + r"\s*\n\s*(\d+)\s*\n\s*([\d/\- ]+?)\s*\n\s*(\d+)\s*\n\s*([\d/\- ]+)",
        text,
    )
    if m:
        return f"{clean(m.group(2))} in x {clean(m.group(4))} in"
    return ""


def _extract_dimensions(spec: Specimen, text: str) -> None:
    """Overall size, leaf/panel size (if present) and area for a specimen."""
    spec.overall_size = _size_after(text, r"Overall size")
    spec.leaf_size = _size_after(text, r"Panel size")
    area = first(r"\(?\s*([\d.]+)\s*(?:ft2|ft²|sq\.?\s*ft)\)?", text)
    if area:
        spec.area = f"{area} ft2"


def _daylight_openings(region: str) -> str:
    """Distinct 'W X H' glass daylight-opening sizes found in a region."""
    vals: List[str] = []
    for m in re.finditer(r"\d[\d/\-]*\s*[Xx]\s*\d[\d/\-]*", region):
        v = clean(m.group(0)).replace(" x ", " X ")
        if v not in vals:
            vals.append(v)
    return "; ".join(vals)


def _overall_result(text: str) -> str:
    if re.search(r"met (?:he |the )?(?:performance )?requirements", text, re.I) or re.search(
        r"satisf(?:ies|y) the (?:cyclic load )?requirements", text, re.I
    ):
        return "Pass - meets the requirements of the referenced protocols"
    if re.search(r"Class\s*[A-Z]+\s*[-–]\s*[A-Z]{1,3}\d", text):
        return "Pass - product rating achieved"
    return ""


# --------------------------------------------------------------------------- #
# Construction: tables
# --------------------------------------------------------------------------- #

_HEADER_WORDS = {
    "member", "material", "detail", "description", "quantity", "location",
    "frame member", "panel member", "glass type", "drawing number", "type",
}


def _is_header_row(row: List[str]) -> bool:
    return all(c.strip().lower() in _HEADER_WORDS for c in row) and len(row) >= 2


def _row_to_three(row: List[str]) -> Optional[tuple]:
    """Map a cleaned table row to a (col1, col2, col3) triple."""
    if len(row) == 3:
        return row[0], row[1], row[2]
    if len(row) == 2:
        return row[0], "", row[1]
    if len(row) > 3:
        return row[0], row[1], " ".join(row[2:])
    return None


# NAFS construction-section labels that each own exactly one ruled table.
_NAFS_SECTION_LABELS = [
    "FRAME CONSTRUCTION", "PANEL CONSTRUCTION", "REINFORCEMENT",
    "GLAZING DETAILS", "WEATHERSTRIPPING", "DRAINAGE", "HARDWARE",
]


def _nafs_section_tables(doc: Document) -> Dict[str, Table]:
    """Pair each construction label with its table by per-page ordering.

    On a page where the count of known section labels equals the count of
    ruled tables, the i-th label maps to the i-th table. This survives the
    header/data column drift in NAFS tables far better than keyword guessing.
    """
    mapping: Dict[str, Table] = {}
    for page in doc.pages:
        labels = [lab for lab in _ordered_labels(page.text, _NAFS_SECTION_LABELS)]
        if labels and len(labels) == len(page.tables):
            for lab, table in zip(labels, page.tables):
                mapping.setdefault(lab, table)
    return mapping


def _ordered_labels(text: str, labels: List[str]) -> List[str]:
    found = []
    for lab in labels:
        m = re.search(re.escape(lab), text, re.I)
        if m:
            found.append((m.start(), lab))
    return [lab for _, lab in sorted(found)]


def _frame_from_table(table: Table) -> List[FrameMember]:
    members = []
    for row in table:
        if _is_header_row(row):
            continue
        triple = _row_to_three(row)
        if triple:
            members.append(FrameMember(member=triple[0], material=triple[1], detail=triple[2]))
    return members


def _hardware_from_table(table: Table) -> List[HardwareItem]:
    items = []
    for row in table:
        if _is_header_row(row):
            continue
        triple = _row_to_three(row)
        if triple:
            items.append(
                HardwareItem(description=triple[0], quantity=triple[1], location=triple[2])
            )
    return items


def _glazing_from_table(table: Table) -> Glazing:
    g = Glazing()
    kv = {clean(r[0]).lower(): clean(" ".join(r[1:])) for r in table if len(r) >= 2}
    g.glass_type = kv.get("glass type", "")
    for key, val in kv.items():
        if "glazing construction" in key or "glass makeup" in key:
            g.makeup = val
        elif "glazing method" in key:
            g.method = val
        elif "glazing bite" in key or key == "bite":
            g.bite = val
        elif "daylight opening" in key:
            g.daylight_opening = val
        elif "overall" in key or "thickness" in key:
            g.overall_thickness = val
    return g


def _looks_like_glazing_table(table: Table) -> bool:
    return any(clean(r[0]).lower() == "glass type" for r in table if r)


# --------------------------------------------------------------------------- #
# NAFS parser
# --------------------------------------------------------------------------- #


def _parse_nafs(doc: Document, report: Report) -> None:
    text = doc.full_text
    report.standard_family = FAMILY_NAFS
    report.client = labeled(text, r"RENDERED TO") or labeled(text, r"CLIENT INFORMATION")
    report.client_location = _address_after(text, r"CLIENT INFORMATION", report.client)
    report.laboratory = labeled(text, r"TEST LABORATORY")
    report.laboratory_location = _address_after(text, r"TEST LABORATORY", report.laboratory)

    specimens = _parse_nafs_specimens(doc)
    if not specimens:
        report.warnings.append("No specimen summary blocks were found.")
        specimens = [Specimen()]

    # Dimensions and construction are described once and shared by the
    # specimens (they are the same product in different frames).
    dims_spec = Specimen()
    _extract_dimensions(dims_spec, text)

    section_tables = _nafs_section_tables(doc)
    shared = _nafs_construction(doc, section_tables)

    daylight = shared.glazing.daylight_opening if shared.glazing else ""
    for spec in specimens:
        if not spec.overall_size:
            spec.overall_size = dims_spec.overall_size
        if not spec.leaf_size:
            spec.leaf_size = dims_spec.leaf_size
        if not spec.area:
            spec.area = dims_spec.area
        spec.daylight_opening = daylight
        spec.construction = _copy_construction(shared)
    report.specimens = specimens
    _nafs_results(doc, report)


def _parse_nafs_specimens(doc: Document) -> List[Specimen]:
    page1 = doc.pages[0].text if doc.pages else ""
    blocks = re.split(r"Test Specimen\s*#\s*(\d+)", page1)
    specimens: List[Specimen] = []
    # re.split keeps the captured id; iterate in (id, body) pairs.
    for i in range(1, len(blocks), 2):
        sid = blocks[i].strip()
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        spec = Specimen(specimen_id=sid)
        body_lines = _lines(body)
        if body_lines:
            spec.label = body_lines[0]
            if len(body_lines) > 1 and re.match(r"^[\w\-/]+$", body_lines[1]):
                spec.model = body_lines[1]
        spec.product_designator = _field_after(body, "Primary Product Designator")
        spec.design_pressure = _field_after(body, "Design Pressure")
        spec.air_infiltration = _field_after(body, "Air Infiltration")
        spec.air_exfiltration = _field_after(body, "Air Exfiltration")
        spec.water_penetration = _field_after(body, "Water Penetration Resistance Test Pressure")
        specimens.append(spec)
    _resolve_see_specimen(specimens)
    return specimens


def _field_after(text: str, label: str) -> str:
    """First non-empty line after ``label`` within a block."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.search(re.escape(label), line, re.I):
            for nxt in lines[i + 1:]:
                if clean(nxt):
                    return clean(nxt)
    return ""


def _resolve_see_specimen(specimens: List[Specimen]) -> None:
    """Replace 'See Specimen #1' references with the referenced value."""
    by_id = {s.specimen_id: s for s in specimens}
    for spec in specimens:
        for attr in ("air_infiltration", "air_exfiltration", "water_penetration"):
            val = getattr(spec, attr)
            ref = re.search(r"See Specimen\s*#?\s*(\d+)", val, re.I)
            if ref and ref.group(1) in by_id:
                setattr(spec, attr, getattr(by_id[ref.group(1)], attr))


def _address_after(text: str, label: str, name: str) -> str:
    """The address lines that follow a label/name block (best effort)."""
    blk = section(text, label, ["PROJECT SUMMARY", "TEST METHODS", "PRODUCT TYPE", "SECTION"])
    lines = _lines(blk)
    if name and lines and clean(lines[0]) == clean(name):
        lines = lines[1:]
    addr = [ln for ln in lines[:3] if not re.match(r"^\d{3}[-.\s]?\d{3}", ln)]
    return ", ".join(addr[:2])


def _nafs_construction(doc: Document, section_tables: Dict[str, Table]) -> Construction:
    con = Construction()
    text = doc.full_text
    if "FRAME CONSTRUCTION" in section_tables:
        con.frame = _frame_from_table(section_tables["FRAME CONSTRUCTION"])
    if "HARDWARE" in section_tables:
        con.hardware = _hardware_from_table(section_tables["HARDWARE"])
    glaz_table = section_tables.get("GLAZING DETAILS")
    if glaz_table and _looks_like_glazing_table(glaz_table):
        con.glazing = _glazing_from_table(glaz_table)
    else:
        for page in doc.pages:  # fall back to any glazing-shaped table
            for t in page.tables:
                if _looks_like_glazing_table(t):
                    con.glazing = _glazing_from_table(t)
                    break
    # Raw multi-line sections; boilerplate is stripped later in analyze().
    con.raw_text = {
        "frame": section(text, r"FRAME CONSTRUCTION", ["PANEL CONSTRUCTION", "REINFORCEMENT"]),
        "glazing": section(text, r"GLAZING DETAILS", ["WEATHERSTRIPPING", "DRAINAGE"]),
        "hardware": section(text, r"HARDWARE", ["SCREEN CONSTRUCTION", "INSTALLATION"]),
    }
    return con


def _nafs_results(doc: Document, report: Report) -> None:
    """Attribute test results to specimens using only the TEST RESULTS region.

    The page-1 summary repeats the "Test Specimen #N" headings, so results are
    read from the region beginning at the first "TEST RESULTS" heading, split
    by specimen there.
    """
    text = doc.full_text
    rm = re.search(r"TEST RESULTS\s*:?", text, re.I)
    region = text[rm.start():] if rm else text
    # The shared "General Notes" block names other tests and would otherwise
    # bleed false positives into the last specimen; cut it off.
    gn = re.search(r"General Notes", region, re.I)
    if gn:
        region = region[: gn.start()]
    parts = re.split(r"Test Specimen\s*#?\s*(\d+)", region)
    blocks: Dict[str, str] = {}
    for i in range(1, len(parts), 2):
        sid = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        blocks[sid] = blocks.get(sid, "") + "\n" + body

    for spec in report.specimens:
        blk = blocks.get(spec.specimen_id, "")
        results: Dict[str, str] = {}
        if re.search(r"OPERATING FORCE", blk, re.I):
            results["Operating Force"] = "Pass - within allowable"
        if re.search(r"AIR LEAKAGE", blk, re.I):
            results["Air Leakage"] = "Pass"
        if re.search(r"WATER PENETRATION", blk, re.I) and re.search(r"Pass|No Leakage", blk, re.I):
            results["Water Penetration"] = "Pass - No leakage"
        if re.search(r"UNIFORM LOAD", blk, re.I):
            results["Uniform Load (structural)"] = "Pass"
        if re.search(r"FORCED ENTRY RESISTANCE", blk, re.I) and re.search(r"Pass|No Entry", blk, re.I):
            results["Forced Entry Resistance"] = "Pass - No entry"
        if re.search(r"CORNER WELD\s*Pass", blk, re.I):
            results["Thermoplastic Corner Weld"] = "Pass"
        if re.search(r"DEGLAZING", blk, re.I) and re.search(r"Pass", blk, re.I):
            results["Deglazing"] = "Pass"
        spec.results = results


# --------------------------------------------------------------------------- #
# TAS parser
# --------------------------------------------------------------------------- #


def _parse_tas(doc: Document, report: Report) -> None:
    text = doc.full_text
    report.standard_family = FAMILY_TAS
    # The scope sentence reads "<Laboratory> was contracted by <client> to perform..."
    report.laboratory = first(r"([A-Z][\w&.,'()\- ]+?)\s+was\s+contracted\s+by", text)
    if not report.laboratory and re.search(r"Intertek", text):
        report.laboratory = "Intertek Building & Construction"
    report.laboratory_location = first(
        r"(\d{3,5}[^\n]*\n[^\n]*(?:California|CA|PA|Pennsylvania|Florida|FL)[^\n]*\d{5})",
        text,
    ).replace("\n", ", ")
    report.client = labeled(text, r"REPORT ISSUED TO") or first(r"TEST REPORT FOR\s+(.+)", text)
    report.client_location = _address_after(text, r"REPORT ISSUED TO", report.client)

    spec = Specimen(specimen_id="1")
    spec.label = report.series_model
    _extract_dimensions(spec, text)

    # Design pressure from the Summary of Test Results.
    spec.design_pressure = first(
        r"DESIGN PRESSURE[\s\S]{0,80}?([+\-]?\s*\d+\s*/\s*[+\-]?\s*\d+\s*psf)", text
    ) or first(r"([+\-]\s*\d+\s*/\s*[-+]?\s*\d+\s*psf)", text)
    spec.air_infiltration = first(
        r"Air Leakage,\s*Infiltration[\s\S]{0,120}?(<?\s*[\d.]+\s*cfm/ft2)", text
    )
    wp = re.search(
        r"Water Penetration,[\s\S]{0,160}?at\s*([\d.]+\s*psf)[\s\S]{0,40}?(Pass|Fail)",
        text,
        re.I,
    )
    if wp:
        spec.water_penetration = f"{clean(wp.group(2))} at {clean(wp.group(1))}"

    spec.construction = _tas_construction(text)
    spec.daylight_opening = _daylight_openings(
        section(text, r"DAYLIGHT OPENING", [r"Drainage", r"Hardware\s*:"])
    )
    spec.results = _tas_results(text)
    report.specimens = [spec]


def _tas_construction(text: str) -> Construction:
    con = Construction()
    frame_sec = section(text, r"Frame Construction", ["JOINERY TYPE", "Reinforcement", "Glazing"])
    con.frame = _chunk_members(frame_sec)

    glaz_sec = section(text, r"Glazing\s*:", [r"Drainage", r"Hardware\s*:"])
    con.glazing = _tas_glazing(glaz_sec)

    if re.search(r"Hardware:\s*No Hardware", text, re.I):
        con.hardware = []
    else:
        hw_sec = section(text, r"Hardware\s*:", [r"Drainage", r"SECTION", r"TEST RESULTS"])
        con.hardware = _chunk_hardware(hw_sec)

    # Raw multi-line sections; boilerplate is stripped later in analyze().
    con.raw_text = {
        "frame": frame_sec,
        "glazing": glaz_sec,
        "hardware": section(text, r"Hardware\s*:", [r"SECTION", r"TEST RESULTS"]),
    }
    return con


def _chunk_members(sec: str) -> List[FrameMember]:
    """Chunk a MEMBER/MATERIAL/DESCRIPTION block into rows of three."""
    lines = _lines(sec)
    # Drop leading header tokens.
    while lines and lines[0].lower() in _HEADER_WORDS:
        lines.pop(0)
    members = []
    for i in range(0, len(lines) - 2, 3):
        members.append(FrameMember(member=lines[i], material=lines[i + 1], detail=lines[i + 2]))
    return members


def _chunk_hardware(sec: str) -> List[HardwareItem]:
    lines = _lines(sec)
    while lines and lines[0].lower() in _HEADER_WORDS:
        lines.pop(0)
    items = []
    for i in range(0, len(lines) - 2, 3):
        items.append(
            HardwareItem(description=lines[i], quantity=lines[i + 1], location=lines[i + 2])
        )
    return items


def _tas_glazing(sec: str) -> Glazing:
    """Parse the TAS glazing block.

    The four column headers (GLASS TYPE / OVERALL THICKNESS / GLASS MAKEUP /
    GLAZING METHOD) all appear before any data, so the values are recovered
    positionally from the data lines that follow: the thickness is the first
    measurement, the method is the "Wet/Dry glazed..." line, the glass type is
    everything before the thickness, and the makeup is everything between.
    """
    g = Glazing()
    lines = _lines(sec)
    start = 0
    for i, ln in enumerate(lines):
        if re.search(r"GLAZING METHOD", ln, re.I):
            start = i + 1
            break
    data: List[str] = []
    for ln in lines[start:]:
        if re.fullmatch(r"(LOCATION|DAYLIGHT OPENING|QUANTITY)", ln, re.I):
            break
        data.append(ln)

    thickness_idx = next(
        (i for i, d in enumerate(data) if re.fullmatch(r'[\d.]+"', d)), None
    )
    method_idx = next(
        (i for i, d in enumerate(data) if re.match(r"(Wet glazed|Dry glazed|Set from)", d, re.I)),
        len(data),
    )
    if thickness_idx is not None:
        g.overall_thickness = data[thickness_idx]
        g.glass_type = " ".join(data[:thickness_idx])
        g.makeup = " ".join(data[thickness_idx + 1:method_idx])
    g.method = " ".join(data[method_idx:])
    g.bite = first(r"GLASS BITE[\s\S]{0,120}?(\d+/\d+\")", sec)
    return g


def _tas_results(text: str) -> Dict[str, str]:
    results: Dict[str, str] = {}
    air = first(r"Air Leakage,\s*Infiltration[\s\S]{0,120}?(<?\s*[\d.]+\s*cfm/ft2)", text)
    if air:
        results["Air Leakage (TAS 202)"] = air
    if re.search(r"Water Penetration,[\s\S]{0,200}?(Pass|No leakage)", text, re.I):
        results["Water Penetration (TAS 202)"] = "Pass - No leakage"
    if re.search(r"Forced Entry Resistance,[\s\S]{0,80}?(Pass|No entry)", text, re.I):
        results["Forced Entry Resistance (TAS 202)"] = "Pass - No entry"
    if re.search(r"TAS 201", text) and not re.search(r"\bFail\b", text):
        if re.search(r"satisfies the large missile requirements|met the requirements of Section 1626", text, re.I):
            results["Large Missile Impact (TAS 201)"] = "Pass"
    if re.search(r"TAS 203", text) and re.search(
        r"satisfy the cyclic load requirements", text, re.I
    ):
        results["Cyclic Wind Pressure (TAS 203)"] = "Pass"
    if re.search(r"No signs of failure[\s\S]{0,80}TAS 202", text, re.I):
        results["Structural (TAS 202)"] = "Pass"
    return results


# --------------------------------------------------------------------------- #
# Generic fallback
# --------------------------------------------------------------------------- #


def _parse_generic(doc: Document, report: Report) -> None:
    report.standard_family = FAMILY_GENERIC
    report.warnings.append(
        "Report layout was not recognised as TAS or NAFS; only top-level "
        "identity fields were extracted."
    )
    text = doc.full_text
    report.client = labeled(text, r"RENDERED TO") or labeled(text, r"REPORT ISSUED TO")
    spec = Specimen(specimen_id="1")
    _extract_dimensions(spec, text)
    report.specimens = [spec]


# --------------------------------------------------------------------------- #
# Construction copy helper
# --------------------------------------------------------------------------- #


def _copy_construction(con: Construction) -> Construction:
    return Construction(
        frame=[FrameMember(m.member, m.material, m.detail) for m in con.frame],
        glazing=Glazing(**vars(con.glazing)) if con.glazing else None,
        hardware=[HardwareItem(h.description, h.quantity, h.location) for h in con.hardware],
        raw_text=dict(con.raw_text),
    )


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #


def _boilerplate(doc: Document) -> set:
    """Lines that repeat on many pages (running headers/footers) and so are
    noise rather than content. Short lines are excluded to protect real data
    tokens such as 'PVC' or 'Extruded'."""
    from collections import Counter

    counts: Counter = Counter()
    for page in doc.pages:
        seen = {" ".join(ln.split()) for ln in page.text.splitlines()}
        for norm in seen:
            if len(norm) >= 15:
                counts[norm] += 1
    return {norm for norm, n in counts.items() if n >= 3}


_NOISE_RE = re.compile(
    r"(?i)^(page\s+\d+\s+of\b|version:|report\s+no\b|report\s+date:|revised\s+report"
    r"|telephone:|facsimile:|rt-r-amer|test\s+report\s+for\b|date:\s*\d|www\.|©|"
    r"\(continued\)|test\s+specimen\s+description)"
)


def _finalize_raw(multiline: str, boiler: set) -> str:
    """Strip running headers/footers from a captured section and collapse it."""
    kept = []
    for ln in multiline.splitlines():
        norm = " ".join(ln.split())
        if not norm or norm in boiler or _NOISE_RE.match(norm):
            continue
        kept.append(norm)
    return clean(" ".join(kept))


def analyze(doc: Document) -> Report:
    """Analyze an already-extracted :class:`Document`."""
    report = Report(source_file=doc.source)
    text = doc.full_text
    family = detect_family(text)

    _extract_identity(doc, report)
    if family == FAMILY_NAFS:
        _parse_nafs(doc, report)
    elif family == FAMILY_TAS:
        _parse_tas(doc, report)
    else:
        _parse_generic(doc, report)

    report.overall_result = _overall_result(text)
    report.revisions = _extract_revisions(text)

    # Tidy the raw-text safety net by removing repeated page headers/footers.
    boiler = _boilerplate(doc)
    for spec in report.specimens:
        rt = spec.construction.raw_text
        for key in list(rt):
            rt[key] = _finalize_raw(rt[key], boiler)
    return report


def analyze_pdf(path: str, password: str = "") -> Report:
    """Load a PDF and analyze it in one step."""
    doc = load_document(path, password=password)
    report = analyze(doc)
    report.source_file = path
    return report


def _extract_revisions(text: str) -> List[Dict[str, str]]:
    revs: List[Dict[str, str]] = []
    for m in re.finditer(
        r"\b(R?\d+)\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+([A-Za-z0-9/ ]+?)\s+([A-Z][^\n]{4,60})",
        text,
    ):
        revs.append(
            {
                "revision": clean(m.group(1)),
                "date": clean(m.group(2)),
                "description": clean(m.group(4)),
            }
        )
    return revs[:10]
