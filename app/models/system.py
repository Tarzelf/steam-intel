"""System and logging models."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class CollectionRun(Base):
    """Track collection job runs."""

    __tablename__ = "collection_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collector_name = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(20), default="running")  # 'running', 'completed', 'failed'
    records_processed = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ApiLog(Base):
    """API request logging."""

    __tablename__ = "api_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    client_ip = Column(String(45))
    response_status = Column(Integer)
    response_time_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
