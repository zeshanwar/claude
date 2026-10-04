"""mysql2ch - convert MySQL CREATE TABLE statements to ClickHouse DDL."""
from .converter import convert, convert_table, parse_tables, map_type

__version__ = "0.1.0"
__all__ = ["convert", "convert_table", "parse_tables", "map_type", "__version__"]
