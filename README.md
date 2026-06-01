# Fenestration Test-Report Analyzer

Scans **window/door building-code test report PDFs** and extracts structured
product information — identity, performance ratings, and the frame / glazing /
hardware construction of every test specimen — into **per-report JSON**, a
**flat one-row-per-specimen CSV**, and an **Excel summary in the FX/SD
"TR Summary" template layout** (one row per specimen, windows routed to the
`FX Temp.` sheet and doors to `SD Temp.`).

## Two extraction backends

| Backend | Flag | Needs | Handles |
| ------- | ---- | ----- | ------- |
| **AI (Claude)** | `--mode ai` | `ANTHROPIC_API_KEY` (small cost/report) | **Any** lab/format — reads the report directly into the fields |
| **Rules** | `--mode rules` | nothing (offline) | The two built-in layouts below |

Default is **`--mode auto`**: AI when `ANTHROPIC_API_KEY` is set, otherwise the
rules parser. Both backends produce the same JSON / CSV / XLSX output.

The rules parser recognises two common layouts, with a generic fallback:

| Family | Example standard | Layout | Specimens |
| ------ | ---------------- | ------ | --------- |
| **TAS** | TAS 201 / 202 / 203 (Florida Building Code, HVHZ) | numbered `SECTION` headers, unruled tables | usually one |
| **NAFS** | AAMA/WDMA/CSA 101/I.S.2/A440 | labelled headers, ruled tables | often several |

For the many other lab formats out there, use **AI mode** — it needs no
per-lab code.

## What it extracts

**Per report:** report number + revision, standard family, test standards,
testing laboratory + location, client + location, product type, series/model,
report/issue/revision/test/completion dates, overall pass-fail, and the
revision log.

**Per specimen:** id / label / model, primary product designator, design
pressure, air infiltration & exfiltration, water-penetration test pressure,
overall size, leaf/panel size, glass daylight opening, individual test results
(impact, structural, water, forced-entry, cyclic, deglazing, …), and the
construction:

- **Frame** — member, material, detail (e.g. `Head, sill and jambs · PVC · Extruded`)
- **Glazing** — glass type, thickness, make-up, method, bite, daylight opening
- **Hardware** — description, quantity, location

When a construction section can't be fully structured, its cleaned source text
is preserved under `construction.raw_text` so nothing is silently lost.

## Install

```bash
pip install -r requirements.txt
# or, to get the `report-analyzer` command on your PATH:
pip install -e .
```

PyMuPDF is the core dependency (openpyxl is used only for `--xlsx`). PyMuPDF
is used because these reports are commonly AES-encrypted (with an empty user
password) and contain ruled tables; PyMuPDF decrypts and lays both out
natively with no system packages. It is isolated in
`report_analyzer/extraction.py`, so the backend can be swapped if needed.

## Usage

### Command line

```bash
# Analyze two reports: print summaries, write JSON per report + a combined CSV
python -m report_analyzer reportA.pdf reportB.pdf \
    --json-dir output --csv output/summary.csv --print

# Scan a whole folder of PDFs
python -m report_analyzer ./reports --json-dir output --csv output/summary.csv

# Excel summary in the FX/SD "TR Summary" layout (fresh workbook)
python -m report_analyzer ./reports --xlsx output/TR_Summary.xlsx

# ...or append the rows into a copy of your own template workbook
python -m report_analyzer ./reports --xlsx output/filled.xlsx \
    --xlsx-template TR_Summary_Template.xlsx

# Encrypted PDF with a user password
python -m report_analyzer secured.pdf --password "hunter2" --print

# AI extraction (handles any lab format) — set your key first
export ANTHROPIC_API_KEY=sk-ant-...        # Windows: set ANTHROPIC_API_KEY=sk-ant-...
python -m report_analyzer ./reports --mode ai --xlsx output/TR_Summary.xlsx
```

### Picking a backend

`--mode auto` (default) uses AI when `ANTHROPIC_API_KEY` is set, else the rules
parser. Force one with `--mode ai` or `--mode rules` (`--ai` / `--rules` are
shortcuts). AI mode reads each report with Claude (`--model`, default
`claude-opus-4-8`) into the exact same fields, so it handles formats the rules
parser has never seen. Get a key at <https://console.anthropic.com>; the long
instruction prompt is cached, so batch runs stay cheap.

| Option | Meaning |
| ------ | ------- |
| `--json-dir DIR` | write one `<report-number>.json` per report into `DIR` |
| `--csv FILE` | write a flat one-row-per-specimen summary across all inputs |
| `--xlsx FILE` | write an Excel summary in the FX/SD "TR Summary" layout |
| `--xlsx-template SRC` | with `--xlsx`, append rows into a copy of template `SRC` instead of a fresh workbook |
| `--mode {auto,ai,rules}` | extraction backend (default `auto`) |
| `--ai` / `--rules` | shortcuts for `--mode ai` / `--mode rules` |
| `--model` | Claude model for AI mode (default `claude-opus-4-8`) |
| `--print` | print a readable summary for each report |
| `--password` | password for encrypted PDFs (default: empty) |
| `--quiet` | suppress progress messages |

### Excel ("TR Summary") output

`--xlsx` writes a workbook with two sheets matching the customer template:

- **`FX Temp.`** (fixed windows): `Test Report # · Report Date · Specimen # ·
  DP (psf) · Test Standard · Frame Size · D.L.O. Size · Description ·
  Glass (Ext.→Int.) · Misc. Note`
- **`SD Temp.`** (sliding/patio doors): the same, plus `Leaf Size` and split
  `Glass – Primary Leaf` / `Glass – Secondary Leaf` columns.

Each specimen is one row; products are routed to `FX`/`SD` by product type.
Dates prefer the revised report date, design pressure is normalised to the
psf column, and glass make-up / standards are written one item per line.

### As a library

```python
from report_analyzer import analyze_pdf
from report_analyzer.export import report_to_json, write_csv

report = analyze_pdf("reportB.pdf")
print(report.report_number, report.overall_result)
for spec in report.specimens:
    print(spec.label, spec.design_pressure, spec.product_designator)

print(report_to_json(report))      # full nested JSON
write_csv([report], "summary.csv") # flat CSV (one row per specimen)
```

### In VS Code

The project ships with `.vscode/launch.json` and `.vscode/tasks.json`:

1. **File → Open Folder…** and pick the project folder.
2. Install the **Python** extension (Microsoft) if prompted, and pick a
   Python interpreter (bottom-right status bar, or *Python: Select Interpreter*).
3. Install dependencies once: **Terminal → Run Task… → "Install dependencies"**
   (or run `python -m pip install -r requirements.txt` in the terminal).
4. Put PDFs in the `reports/` folder, then **Run and Debug (F5) → "Analyze:
   reports/ folder"** — or **"Analyze: choose folder or file…"** to be prompted
   for any path. Results land in `output/` (open `output/TR_Summary.xlsx`).

### Simple launcher (any OS)

Put PDFs in the `reports/` folder, then run:

```bash
python run.py                 # analyzes ./reports
python run.py path/to/folder  # or any folder / PDFs you pass
```

`run.py` installs dependencies on first run, writes
`output/TR_Summary.xlsx` + `output/summary.csv`, and opens the output folder
on desktop systems. On Windows you can also just double-click `run.py`. See
`START_HERE_Windows.txt`.

## Try it without any real reports

The real example reports are confidential, so they are **not** committed here
(`*.pdf` is git-ignored). A generator fabricates a structurally similar report
so you can run the whole pipeline:

```bash
python samples/make_sample_report.py
python -m report_analyzer samples/sample_tas_report.pdf --print
```

## How it works

```
PDF ─▶ extraction.py ─▶ Document(pages: text + cleaned tables)
                              │
                ┌─────────────┴─────────────┐
        parsing.py (rules)           ai_extract.py (Claude)
        detect TAS / NAFS            one structured-output call,
        regex + tables               any format → the schema
                └─────────────┬─────────────┘
                              ▼
                          Report (models.py)
                              │
              export.py ─▶ JSON (full) + CSV (flat)
              xlsx_export.py ─▶ Excel (FX/SD "TR Summary" layout)
```

- **`extraction.py`** is the only module that touches PyMuPDF. It returns plain
  `Document`/`Page` objects (text + tables), so all parsing is unit-testable
  from raw strings with no PDF.
- Ruled NAFS tables are reconstructed by dropping the empty padding cells each
  row is split into, then pairing each construction section with its table by
  per-page ordering. Unruled TAS tables are recovered by chunking the text
  stream. Repeated page headers/footers are detected and stripped.

## Extending to a new lab format

1. Add a detector branch in `detect_family`.
2. Write a `_parse_<family>` function that fills a `Report` (reuse the shared
   helpers: `labeled`, `labeled_longest`, `section`, `first`, the table
   helpers, and `_extract_dimensions`).
3. Add a synthetic fixture and tests in `tests/test_parsing.py`.

## Limitations

- Targets fenestration test reports in the two layouts above; other report
  types fall back to identity-only extraction (and are flagged in `warnings`).
- Drawing/CAD pages are not interpreted (only their text is read).
- Extraction is heuristic. The high-value identity and performance fields are
  reliable; deeply formatted construction tables are best-effort, with the raw
  section text always retained as a safety net.
- **Confidentiality:** test reports belong to the labs/clients that produced
  them. Generated JSON/CSV/XLSX contains that data — `output/` and `*.pdf` are
  git-ignored so report content is never committed by accident.

## Tests

```bash
python -m pytest tests/ -q     # if pytest is installed
python tests/test_parsing.py   # otherwise runs as a plain script
```
