from __future__ import annotations

from spectus._core.exporter import records_to_csv


def test_empty_records():
    assert records_to_csv([]) == ""


def test_basic_csv():
    csv = records_to_csv([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    lines = csv.strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,x"
    assert lines[2] == "2,y"


def test_csv_handles_missing_fields():
    csv = records_to_csv([{"a": 1}, {"a": 2, "b": "extra"}])
    lines = csv.strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,"
    assert lines[2] == "2,extra"


def test_list_value_joined():
    csv = records_to_csv([{"tags": ["red", "blue"]}])
    assert "red; blue" in csv
