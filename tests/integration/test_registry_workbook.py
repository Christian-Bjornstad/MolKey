"""The protected Excel snapshot follows committed registry changes."""

from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

from molkey.application.patient_key_service import PatientKeyService
from molkey.infrastructure.database import transaction
from molkey.infrastructure.migrations import migrate


def _cells(path: Path) -> list[str]:
    with ZipFile(path) as workbook:
        assert workbook.testzip() is None
        for member in workbook.namelist():
            if member.endswith((".xml", ".rels")):
                ElementTree.fromstring(workbook.read(member))
        root = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [node.text or "" for node in root.findall(".//x:c/x:is/x:t", ns)]


def test_excel_snapshot_contains_every_committed_mapping_and_uppercase_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    first = service.get_or_create("26oum12345", "cfb")
    second = service.process_batch(["26oum88888", "26OUM77777"], "anb")

    assert service.workbook_path.exists()
    cells = _cells(service.workbook_path)
    for record in [first, *second.items]:
        assert record.patient_id in cells
        assert record.pseudonymous_key in cells
    assert "26oum12345" not in cells
    assert "CFB" in cells and "ANB" in cells


def test_locked_workbook_does_not_undo_database_commit(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    with patch("molkey.infrastructure.registry_workbook.os.replace", side_effect=PermissionError("open in Excel")):
        record = service.get_or_create("26oum12345", "cfb")

    assert service.lookup_by_patient("26OUM12345") == record
    assert service.workbook_error == "open in Excel"
    assert service.refresh_registry_workbook()
    assert record.patient_id in _cells(service.workbook_path)


def test_search_reaches_rows_outside_visible_page_and_escapes_wildcards(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"
    migrate(db_path)
    service = PatientKeyService(db_path)
    with transaction(db_path) as conn:
        conn.executemany(
            "INSERT INTO patient_keys (patient_id, pseudonymous_key, created_by) VALUES (?, ?, 'CFB')",
            [(f"26OUM{i:05d}", f"MK{i:016X}") for i in range(510)] + [("SPECIALABC", "MKAAAAAAAAAAAAAAAA")],
        )

    rows, matches, total = service.search_registry("specialabc")
    assert [row.patient_id for row in rows] == ["SPECIALABC"]
    assert (matches, total) == (1, 511)
    rows, matches, total = service.search_registry("26oum")
    assert len(rows) == 500
    assert (matches, total) == (510, 511)
