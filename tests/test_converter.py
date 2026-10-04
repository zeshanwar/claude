from pathlib import Path

import pytest

from mysql2ch import convert, map_type, parse_tables
from mysql2ch.cli import main

EXAMPLE = Path(__file__).parent.parent / "examples" / "access_events.sql"


@pytest.mark.parametrize("mysql,expected", [
    ("int(11)", "Int32"),
    ("int(10) unsigned", "UInt32"),
    ("bigint(20) unsigned", "UInt64"),
    ("tinyint(1)", "Bool"),
    ("tinyint(4)", "Int8"),
    ("smallint", "Int16"),
    ("decimal(10,2)", "Decimal(10, 2)"),
    ("decimal", "Decimal(10, 0)"),
    ("float", "Float32"),
    ("double", "Float64"),
    ("varchar(255)", "String"),
    ("longtext", "String"),
    ("json", "String"),
    ("date", "Date32"),
    ("datetime", "DateTime"),
    ("datetime(3)", "DateTime64(3)"),
    ("timestamp(6)", "DateTime64(6)"),
    ("enum('a','b')", "LowCardinality(String)"),
    ("year", "UInt16"),
    ("bit(1)", "UInt64"),
    ("INT UNSIGNED", "UInt32"),
])
def test_map_type(mysql, expected):
    assert map_type(mysql) == expected


def test_parse_tables():
    tables = parse_tables(EXAMPLE.read_text())
    assert [t.name for t in tables] == ["access_events", "doors"]
    events = tables[0]
    assert events.primary_key == ["tenant_id", "id"]
    assert [c.name for c in events.columns][:3] == ["id", "tenant_id", "badge_id"]
    door_col = next(c for c in events.columns if c.name == "door_id")
    assert door_col.nullable
    assert tables[1].primary_key == ["id"]
    assert tables[1].columns[0].mysql_type.lower() == "int unsigned"


def test_convert_output():
    out = convert(EXAMPLE.read_text())
    assert "`id` UInt64," in out
    assert "`door_id` Nullable(Int32)" in out
    assert "`is_visitor` Bool" in out
    assert "`id` UInt32," in out  # doors.id int unsigned
    assert "COMMENT 'Result of the access attempt'" in out
    assert "ORDER BY (`tenant_id`, `id`);" in out
    assert "ENGINE = ReplacingMergeTree\n" in out
    assert "idx_badge" not in out and "fk_door" not in out


def test_cdc_and_database():
    out = convert(EXAMPLE.read_text(), cdc=True, database="analytics")
    assert "`analytics`.`access_events`" in out
    assert "`_version` UInt64" in out
    assert "ReplacingMergeTree(_version, _is_deleted)" in out


def test_table_without_pk():
    out = convert("CREATE TABLE logs (msg text, ts datetime NOT NULL);")
    assert "ENGINE = MergeTree" in out
    assert "ORDER BY tuple();" in out


def test_cli(tmp_path, capsys):
    outfile = tmp_path / "out.sql"
    assert main([str(EXAMPLE), "-o", str(outfile)]) == 0
    assert "CREATE TABLE IF NOT EXISTS `doors`" in outfile.read_text()


def test_cli_no_tables(tmp_path):
    f = tmp_path / "empty.sql"
    f.write_text("SELECT 1;")
    assert main([str(f)]) == 1
