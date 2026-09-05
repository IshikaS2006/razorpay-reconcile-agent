"""
Run this once to create the tables in Postgres.
Usage: python backend\\init_db.py
"""
from sqlalchemy import inspect, text

from db import Base, engine
import models  # noqa: F401 -- imported so its tables register with Base

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    match_columns = {column["name"] for column in inspector.get_columns("matches")}
    match_missing_columns = {
        "settled_amount": "BIGINT",
        "match_subtype": "VARCHAR",
        "expected_amount_paise": "BIGINT",
        "actual_amount_paise": "BIGINT",
        "amount_gap_paise": "BIGINT",
    }
    with engine.begin() as connection:
        for column_name, column_type in match_missing_columns.items():
            if column_name not in match_columns:
                connection.execute(text(f"ALTER TABLE matches ADD COLUMN {column_name} {column_type}"))
    inspector = inspect(engine)
    batch_run_columns = {column["name"] for column in inspector.get_columns("batch_runs")}
    missing_columns = {
        "records_processed": "INTEGER",
        "total_time_sec": "DOUBLE PRECISION",
        "records_per_sec": "DOUBLE PRECISION",
        "orders_available": "BOOLEAN",
    }
    with engine.begin() as connection:
        for column_name, column_type in missing_columns.items():
            if column_name not in batch_run_columns:
                connection.execute(text(f"ALTER TABLE batch_runs ADD COLUMN {column_name} {column_type}"))
    inspector = inspect(engine)
    table_columns = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in ("matches", "exceptions", "investigations")
    }
    additional_columns = {
        "matches": {"status": "VARCHAR"},
        "exceptions": {"status": "VARCHAR"},
        "investigations": {
            "resolved_at": "TIMESTAMP",
            "resolution_type": "VARCHAR",
            "resolution_action": "TEXT",
        },
    }
    with engine.begin() as connection:
        for table_name, columns in additional_columns.items():
            for column_name, column_type in columns.items():
                if column_name not in table_columns[table_name]:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
    print("Tables created successfully: batch_runs, matches, exceptions, investigations")