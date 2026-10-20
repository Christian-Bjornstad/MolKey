"""Read-only Excel snapshot of the protected patient key registry."""

# ruff: noqa: E501  (Office Open XML namespace declarations are indivisible.)

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from molkey.infrastructure.repositories import PatientKeyRecord

WORKBOOK_NAME = "MolKey-register.xlsx"


def _cell(value: str, reference: str, *, header: bool = False) -> str:
    # Inline strings cannot be evaluated as formulas, even when an identifier
    # starts with =, + or @. Strip XML-illegal control characters.
    safe = "".join(ch for ch in value if ord(ch) >= 32 or ch in "\t\n\r")
    return f'<c r="{reference}" t="inlineStr" s="{1 if header else 0}"><is><t>{escape(safe)}</t></is></c>'


def write_registry_workbook(records: list[PatientKeyRecord], destination: Path) -> None:
    """Atomically replace a searchable workbook without touching the database."""
    if len(records) > 1_048_575:
        raise ValueError("Registry exceeds the Excel worksheet row limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".xlsx", delete=False) as handle:
            temporary = Path(handle.name)
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>""",
            )
            archive.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "xl/workbook.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Register" sheetId="1" r:id="rId1"/></sheets></workbook>""",
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>""",
            )
            archive.writestr(
                "xl/styles.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF24345B"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"/></cellXfs>
</styleSheet>""",
            )
            with archive.open("xl/worksheets/sheet1.xml", "w") as sheet:

                def put(fragment: str) -> None:
                    sheet.write(fragment.encode("utf-8"))

                last = len(records) + 1
                put('<?xml version="1.0" encoding="UTF-8"?>')
                put('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
                put(
                    '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                )
                put(
                    '<cols><col min="1" max="1" width="25" customWidth="1"/><col min="2" max="2" width="22" customWidth="1"/><col min="3" max="3" width="23" customWidth="1"/><col min="4" max="4" width="15" customWidth="1"/></cols>'
                )
                put('<sheetData><row r="1">')
                for column, title in zip("ABCD", ("Pasient-ID", "MolKey", "Opprettet", "Opprettet av"), strict=True):
                    put(_cell(title, f"{column}1", header=True))
                put("</row>")
                for number, record in enumerate(records, 2):
                    put(f'<row r="{number}">')
                    values = (
                        record.patient_id,
                        record.pseudonymous_key,
                        record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                        record.created_by,
                    )
                    for column, value in zip("ABCD", values, strict=True):
                        put(_cell(value, f"{column}{number}"))
                    put("</row>")
                put(f'</sheetData><autoFilter ref="A1:D{last}"/></worksheet>')
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
