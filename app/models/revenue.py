"""Revenue tracking models."""
import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, Integer, BigInteger, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class RevenueRecord(Base):
    """Revenue data from Partner API."""

    __tablename__ = "revenue_records"
    __table_args__ = (
        UniqueConstraint("app_id", "period_start", "period_end", "period_type", name="uq_revenue_period"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    app_id = Column(Integer, nullable=False, index=True)

    # Period
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(20), nullable=False)  # 'daily', 'weekly', 'monthly'

    # Revenue
    gross_revenue_cents = Column(BigInteger)
    net_revenue_cents = Column(BigInteger)
    units_sold = Column(Integer)
    refunds = Column(Integer)

    # Regional breakdown
    region_breakdown = Column(JSONB)

    # Source
    source = Column(String(50), default="partner_api")
    raw_data = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
