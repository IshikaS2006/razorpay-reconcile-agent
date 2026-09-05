"""
SQLAlchemy models -- four tables: batch_runs, matches, exceptions, investigations.
Each pipeline run creates one batch_run row, plus its matches and exceptions.
Each exception can have zero or more investigation results (audit trail).
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
    records_processed = Column(Integer)
    total_time_sec = Column(Float)
    records_per_sec = Column(Float)
    orders_available = Column(Boolean)

    matches = relationship("Match", back_populates="run", cascade="all, delete-orphan")
    exceptions = relationship("Exception_", back_populates="run", cascade="all, delete-orphan")
    investigations = relationship("Investigation", back_populates="run", cascade="all, delete-orphan")
    gl_postings = relationship("GLPosting", back_populates="run", cascade="all, delete-orphan")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("batch_runs.id"))
    settlement_id = Column(String)
    settled_amount = Column(BigInteger)
    matched_entry_id = Column(String)
    tier = Column(String)
    confidence = Column(Float)
    reason = Column(Text)
    match_subtype = Column(String)
    expected_amount_paise = Column(BigInteger)
    actual_amount_paise = Column(BigInteger)
    amount_gap_paise = Column(BigInteger)
    status = Column(String)

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
    status = Column(String)

    run = relationship("BatchRun", back_populates="exceptions")


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("batch_runs.id"))
    exception_reference_id = Column(String)  # reference to Exception_.reference_id
    status = Column(String)  # "explained" (confidence >= 0.7) or "escalated" (confidence < 0.7)
    explanation = Column(Text)  # plain-language explanation from LLM
    confidence = Column(Float)  # 0-1 score
    evidence_used = Column(Text)  # JSON array of dispute log IDs found, or empty string
    reasoning_chain = Column(Text)  # full LLM reasoning for audit trail
    investigated_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    resolution_type = Column(String)
    resolution_action = Column(Text)

    run = relationship("BatchRun", back_populates="investigations")


class GLPosting(Base):
    __tablename__ = "gl_postings"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("batch_runs.id"))
    entry_id = Column(String)
    settlement_id = Column(String)
    debit = Column(BigInteger)
    credit = Column(BigInteger)
    posted_at = Column(DateTime, default=datetime.utcnow)

    # This is a simulated/mock posting for the demo, not a real ledger integration.
    run = relationship("BatchRun", back_populates="gl_postings")