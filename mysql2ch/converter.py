"""Core conversion logic: parse MySQL DDL and emit ClickHouse DDL."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_INT_TYPES = {
    "tinyint": ("Int8", "UInt8"),
    "smallint": ("Int16", "UInt16"),
    "mediumint": ("Int32", "UInt32"),
    "int": ("Int32", "UInt32"),
    "integer": ("Int32", "UInt32"),
    "bigint": ("Int64", "UInt64"),
}

_STRING_TYPES = {
    "char", "varchar", "tinytext", "text", "mediumtext", "longtext",
    "binary", "varbinary", "tinyblob", "blob", "mediumblob", "longblob",
    "json", "time", "set",
}

_SKIP_PREFIXES = ("key ", "index ", "unique ", "constraint ", "foreign ",
                  "fulltext ", "spatial ", "check ")


@dataclass
class Column:
    name: str
    mysql_type: str
    nullable: bool = True
    comment: str | None = None


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)


def map_type(mysql_type: str) -> str:
    """Map a single MySQL column type (e.g. 'int(11) unsigned') to ClickHouse."""
    t = mysql_type.strip().lower()
    m = re.match(r"([a-z]+)\s*(?:\(([^)]*)\))?\s*(.*)", t)
    if not m:
        return "String"
    base, args, rest = m.group(1), m.group(2), m.group(3)
    unsigned = "unsigned" in rest

    if base == "tinyint" and args == "1" and not unsigned:
        return "Bool"
    if base in _INT_TYPES:
        return _INT_TYPES[base][1 if unsigned else 0]
    if base in ("decimal", "numeric", "dec"):
        p, s = 10, 0
        if args:
            parts = [x.strip() for x in args.split(",")]
            p = int(parts[0])
            s = int(parts[1]) if len(parts) > 1 else 0
        return f"Decimal({p}, {s})"
    if base == "float":
        return "Float32"
    if base in ("double", "real"):
        return "Float64"
    if base == "bit":
        return "UInt64"
    if base == "year":
        return "UInt16"
    if base == "date":
        return "Date32"
    if base in ("datetime", "timestamp"):
        precision = int(args) if args and args.strip().isdigit() else 0
        return f"DateTime64({precision})" if precision else "DateTime"
    if base == "enum":
        return "LowCardinality(String)"
    if base in _STRING_TYPES:
        return "String"
    return "String"


def _split_top_level(body: str) -> list[str]:
    """Split on commas that are not inside parentheses or quotes."""
    parts, buf, depth, quote = [], [], 0, None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"', "`"):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def _unquote(name: str) -> str:
    return name.strip().strip("`\"")


def _parse_column(defn: str) -> Column | None:
    m = re.match(r"\s*(`[^`]+`|\"[^\"]+\"|\w+)\s+(.*)", defn, re.S)
    if not m:
        return None
    name, rest = _unquote(m.group(1)), m.group(2)
    tm = re.match(r"([a-zA-Z]+(?:\s*\([^)]*\))?(?:\s+unsigned)?(?:\s+zerofill)?)", rest, re.I)
    mysql_type = tm.group(1) if tm else rest.split()[0]
    nullable = not re.search(r"\bnot\s+null\b", rest, re.I)
    cm = re.search(r"\bcomment\s+'((?:[^'\\]|\\.|'')*)'", rest, re.I)
    comment = cm.group(1) if cm else None
    if re.search(r"\bprimary\s+key\b", rest, re.I):
        nullable = False
    return Column(name, mysql_type.strip(), nullable, comment)


def parse_tables(sql: str) -> list[Table]:
    """Extract every CREATE TABLE statement from a MySQL dump or DDL string."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    sql = re.sub(r"^\s*--.*$", "", sql, flags=re.M)
    tables: list[Table] = []
    pattern = re.compile(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?((?:`[^`]+`|\w+)(?:\.(?:`[^`]+`|\w+))?)\s*\(",
        re.I,
    )
    for m in pattern.finditer(sql):
        name = _unquote(m.group(1).split(".")[-1])
        start, depth, i = m.end(), 1, m.end()
        while i < len(sql) and depth:
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
            i += 1
        body = sql[start:i - 1]
        table = Table(name)
        for defn in _split_top_level(body):
            low = defn.lower().lstrip()
            pk = re.match(r"(?:constraint\s+\S+\s+)?primary\s+key\s*\(", low)
            if pk:
                inner = defn[defn.index("(") + 1:defn.rindex(")")]
                table.primary_key = [_unquote(c.split("(")[0]) for c in inner.split(",")]
                continue
            if low.startswith(_SKIP_PREFIXES):
                continue
            col = _parse_column(defn)
            if col:
                if re.search(r"\bprimary\s+key\b", defn, re.I):
                    table.primary_key = [col.name]
                table.columns.append(col)
        for col in table.columns:
            if col.name in table.primary_key:
                col.nullable = False
        tables.append(table)
    return tables


def convert_table(table: Table, cdc: bool = False, database: str | None = None) -> str:
    """Render one parsed table as a ClickHouse CREATE TABLE statement."""
    lines = []
    for col in table.columns:
        ch_type = map_type(col.mysql_type)
        if col.nullable:
            ch_type = f"Nullable({ch_type})"
        line = f"    `{col.name}` {ch_type}"
        if col.comment:
            line += " COMMENT '" + col.comment.replace("'", "\\'") + "'"
        lines.append(line)
    if cdc:
        lines.append("    `_version` UInt64")
        lines.append("    `_is_deleted` UInt8 DEFAULT 0")

    full_name = f"`{database}`.`{table.name}`" if database else f"`{table.name}`"
    if cdc:
        engine = "ReplacingMergeTree(_version, _is_deleted)"
    elif table.primary_key:
        engine = "ReplacingMergeTree"
    else:
        engine = "MergeTree"
    order_by = ", ".join(f"`{c}`" for c in table.primary_key) if table.primary_key else "tuple()"
    if table.primary_key and len(table.primary_key) > 1:
        order_by = f"({order_by})"

    return (f"CREATE TABLE IF NOT EXISTS {full_name}\n(\n"
            + ",\n".join(lines)
            + f"\n)\nENGINE = {engine}\nORDER BY {order_by};\n")


def convert(sql: str, cdc: bool = False, database: str | None = None) -> str:
    """Convert all CREATE TABLE statements in a MySQL DDL string."""
    return "\n".join(convert_table(t, cdc=cdc, database=database) for t in parse_tables(sql))
