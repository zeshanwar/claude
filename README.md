# mysql2ch

Convert MySQL `CREATE TABLE` statements into ready-to-run **ClickHouse** DDL — including
optional columns for **CDC pipelines** (Debezium → Kafka → ClickHouse).

Moving a MySQL schema to ClickHouse by hand is slow and error-prone: unsigned integers,
`tinyint(1)` booleans, `DECIMAL` precision, `DATETIME(3)` precision, nullability, and
choosing an engine and `ORDER BY` key all need care. `mysql2ch` does it in one command,
with no dependencies.

## Install

```bash
pip install git+https://github.com/zeshanwar/claude.git
```

## Usage

```bash
# Convert a schema file
mysql2ch schema.sql

# Write to a file, prefix with a ClickHouse database, and add CDC columns
mysql2ch schema.sql -o clickhouse.sql --database analytics --cdc

# Pipe straight from mysqldump
mysqldump --no-data mydb | mysql2ch > clickhouse.sql
```

Or from Python:

```python
from mysql2ch import convert
print(convert(open("schema.sql").read(), cdc=True))
```

## Example

Input (MySQL):

```sql
CREATE TABLE `access_events` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `tenant_id` int(11) NOT NULL,
  `door_id` int(11) DEFAULT NULL,
  `event_type` enum('GRANTED','DENIED','FORCED') NOT NULL COMMENT 'Result of the access attempt',
  `is_visitor` tinyint(1) NOT NULL DEFAULT '0',
  `amount` decimal(10,2) DEFAULT NULL,
  `created_at` datetime(3) NOT NULL,
  PRIMARY KEY (`tenant_id`,`id`),
  KEY `idx_door` (`door_id`)
) ENGINE=InnoDB;
```

Output (`--cdc --database analytics`):

```sql
CREATE TABLE IF NOT EXISTS `analytics`.`access_events`
(
    `id` UInt64,
    `tenant_id` Int32,
    `door_id` Nullable(Int32),
    `event_type` LowCardinality(String) COMMENT 'Result of the access attempt',
    `is_visitor` Bool,
    `amount` Nullable(Decimal(10, 2)),
    `created_at` DateTime64(3),
    `_version` UInt64,
    `_is_deleted` UInt8 DEFAULT 0
)
ENGINE = ReplacingMergeTree(_version, _is_deleted)
ORDER BY (`tenant_id`, `id`);
```

## Type mapping

| MySQL | ClickHouse |
|---|---|
| `tinyint(1)` | `Bool` |
| `tinyint` / `smallint` / `mediumint` / `int` / `bigint` | `Int8` / `Int16` / `Int32` / `Int32` / `Int64` (`UInt*` when unsigned) |
| `decimal(p,s)` | `Decimal(p, s)` |
| `float` / `double` | `Float32` / `Float64` |
| `char`, `varchar`, `*text`, `*blob`, `json`, `time`, `set` | `String` |
| `enum(...)` | `LowCardinality(String)` |
| `date` | `Date32` |
| `datetime` / `timestamp` | `DateTime`, or `DateTime64(n)` with fractional precision |
| `year` | `UInt16` |
| `bit(n)` | `UInt64` |

Columns without `NOT NULL` become `Nullable(...)`; primary-key columns are never nullable.

## Engine rules

- Table has a primary key → `ReplacingMergeTree`, `ORDER BY` the primary key
- No primary key → `MergeTree ORDER BY tuple()`
- `--cdc` → adds `_version` and `_is_deleted` and uses `ReplacingMergeTree(_version, _is_deleted)`,
  so updates and deletes from Debezium collapse correctly

Secondary indexes and foreign keys are skipped (ClickHouse doesn't use them the same way).

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- [ ] `PARTITION BY` suggestions for date columns
- [ ] Optional `Enum8` output for `enum` columns
- [ ] Kafka engine table + materialized view generation for CDC topics
- [ ] PostgreSQL input

Contributions welcome — open an issue or PR.

## License

MIT
