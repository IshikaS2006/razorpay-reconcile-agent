"""
Run this once to create the tables in Postgres.
Usage: python backend\\init_db.py
"""
from db import Base, engine
import models  # noqa: F401 -- imported so its tables register with Base

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully: batch_runs, matches, exceptions, investigations")