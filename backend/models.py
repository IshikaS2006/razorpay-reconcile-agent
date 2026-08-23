"""
SQLAlchemy models -- three tables: batch_runs, matches, exceptions.
Each pipeline run creates one batch_run row, plus its matches and exceptions.
"""
from sqlalchemy import Column, Integer, String, Float, BigInteger, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base


class BatchRun(Base):
    __tablename__ = "batch_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_at = Column(DateTime, default=datetime.utcnow)
    llm_available = Column(Boolean)
    total_settlement_batches = Column(Integer)
    matched_batches = Column(Integer)
    match_rate_pct = Column(Float)
    total_exceptions = Column(Integer)
    db_side_exceptions = Column(Integer)

    matches = relationship("Match", back_populates="run", cascade="all, delete-orphan")
    exceptions = relationship("Exception_", back_populates="run", cascade="all, delete-orphan")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("batch_runs.id"))
    settlement_id = Column(String)
    matched_entry_id = Column(String)
    tier = Column(String)
    confidence = Column(Float)
    reason = Column(Text)

    run = relationship("BatchRun", back_populates="matches")


class Exception_(Base):
    __tablename__ = "exceptions"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("batch_runs.id"))
    source = Column(String)
    exception_type = Column(String)
    reference_id = Column(String)
    amount_paise = Column(BigInteger)
    detail = Column(Text)
    recommended_action = Column(Text)

    run = relationship("BatchRun", back_populates="exceptions")