"""Generate a small, fully synthetic TAS-style test report PDF.

The real example reports are confidential client documents and are not stored
in this repository. This script fabricates a structurally similar report so
the analyzer can be demonstrated end-to-end::

    python samples/make_sample_report.py
    python -m report_analyzer samples/sample_tas_report.pdf --print

All names, numbers and results below are invented.
"""

import os

import fitz  # PyMuPDF

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_tas_report.pdf")

FOOTER = (
    "Sample Testing Labs\n"
    "1 Demo Parkway, Demo City, FL 33000\n"
    "www.example-testing.invalid\n"
    "TEST REPORT FOR ACME FENESTRATION\n"
    "Report No.: SAMPLE.01-001-01-R0\n"
)

PAGES = [
    # 1 - cover
    "ACME FENESTRATION\n"
    "FLORIDA BUILDING CODE TEST REPORT\n\n"
    "SCOPE OF WORK\n"
    "TAS 201, TAS 202, AND TAS 203 TESTING ON MODEL = SAMPLE FIXED WINDOW - 60\" X 60\"\n\n"
    "REPORT NUMBER\nSAMPLE.01-001-01-R0\n\n"
    "TEST DATES\n01/05/26 - 01/20/26\n\n"
    "ISSUE DATE\n02/01/26\n",
    # 2 - scope + summary
    "SECTION 1\nSCOPE\n"
    "Sample Testing Labs was contracted by Acme Fenestration to perform TAS 201, TAS 202,\n"
    "and TAS 203 testing in accordance with the Florida Building Code.\n\n"
    "REPORT ISSUED TO\nACME FENESTRATION\n100 Sample Avenue\nDemo City, FL 33000\n\n"
    "SECTION 2\nSUMMARY OF TEST RESULTS\n"
    "Product Type: Fixed Window\n"
    "Series/Model: Sample Fixed Window - 60\" X 60\"\n\n"
    "SPEC. TEST PROTOCOL DESIGN PRESSURE\n"
    "1 TAS 202 +50 / -50 psf\n"
    "1 TAS 201/203 (Large Missile) +50 / -50 psf\n",
    # 3 - test methods
    "SECTION 3\nTEST METHODS\n"
    "TAS 201-94, Impact Test Procedures\n"
    "TAS 202-94, Criteria for Testing Impact & Non Impact Resistant Building Envelope Components\n"
    "TAS 203-94, Criteria for Testing Products Subject to Cyclic Wind Pressure Loading\n",
    # 4 - specimen description + size
    "SECTION 7\nTEST SPECIMEN DESCRIPTION\n"
    "Product Type: Fixed Window\n"
    "Series/Model: Sample Fixed Window - 60\" X 60\"\n\n"
    "Product Size:\nOVERALL, AREA:\nWIDTH\nHEIGHT\n"
    "millimeters\ninches\nmillimeters\ninches\n"
    "Overall size\n1524\n60\n1524\n60\n",
    # 5 - frame + glazing + hardware
    "Frame Construction:\n"
    "MEMBER\nMATERIAL\nDESCRIPTION\n"
    "Head\nAluminum\nExtruded\n"
    "Jambs\nAluminum\nExtruded\n"
    "Sill\nAluminum\nExtruded\n\n"
    "JOINERY TYPE\nDETAIL\nAll corners\nMitred\n\n"
    "Glazing:\n"
    "GLASS TYPE\nOVERALL\nTHICKNESS\nGLASS MAKEUP\nGLAZING METHOD\n"
    "Insulated\nGlass\n1.00\"\n1/4\" Tempered\n1/2 Air Gap\n1/4\" Tempered\n"
    "Dry glazed interior and\nexterior\n"
    "LOCATION\nQUANTITY\nDAYLIGHT OPENING\nGLASS BITE\ninches\n"
    "Single Lite\n1\n56 X 56\n1/2\"\n\n"
    "Drainage: No Drainage was utilized\n"
    "Hardware: No Hardware was utilized\n",
    # 6 - conclusions
    "SECTION 9\nCONCLUSIONS\n"
    "The test specimen satisfies the large missile requirements of TAS 201 and met the\n"
    "requirements of Section 1626 of the Florida Building Code.\n"
    "No signs of failure were observed in any area of the test specimen during the TAS 202\n"
    "testing. The test specimens satisfy the cyclic load requirements of TAS 203.\n",
]


def main() -> None:
    doc = fitz.open()
    for i, body in enumerate(PAGES, start=1):
        page = doc.new_page()
        page.insert_text((54, 60), FOOTER + f"Page {i} of {len(PAGES)}\n", fontsize=8)
        page.insert_text((54, 170), body, fontsize=10)
    doc.save(OUT)
    doc.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
