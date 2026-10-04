"""Command-line interface: mysql2ch schema.sql [-o out.sql] [--cdc] [--database db]"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .converter import convert


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mysql2ch",
        description="Convert MySQL CREATE TABLE statements to ClickHouse DDL.",
    )
    p.add_argument("input", nargs="?", default="-",
                   help="MySQL .sql file (default: read from stdin)")
    p.add_argument("-o", "--output", help="Write result to this file instead of stdout")
    p.add_argument("--cdc", action="store_true",
                   help="Add _version/_is_deleted columns for Debezium/Kafka CDC pipelines")
    p.add_argument("--database", help="Prefix tables with this ClickHouse database name")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    if args.input == "-":
        sql = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as f:
            sql = f.read()

    result = convert(sql, cdc=args.cdc, database=args.database)
    if not result.strip():
        print("No CREATE TABLE statements found.", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
