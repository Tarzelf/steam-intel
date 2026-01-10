"""Analytics and computed models."""
import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, Integer, Date, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class PortfolioBenchmark(Base):
    """Pre-computed portfolio vs market comparison."""

    __tablename__ = "portfolio_benchmarks"
    __table_args__ = (
        UniqueConstraint("benchmark_date", name="uq_portfolio_benchmark_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    benchmark_date = Column(Date, nullable=False, index=True)

    # Portfolio aggregates
    portfolio_total_ccu = Column(Integer)
    portfolio_avg_review_score = Column(Integer)
    portfolio_total_owners_estimate = Column(Integer)

    # Market averages
    market_avg_ccu = Column(Integer)
    market_avg_review_score = Column(Integer)
    market_median_owners = Column(Integer)

    # Computed
    ccu_vs_market_pct = Column(Integer)
    reviews_vs_market_pct = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class GenreScore(Base):
    """Genre scoring for submission evaluation with enhanced velocity data."""

    __tablename__ = "genre_scores"
    __table_args__ = (
        UniqueConstraint("genre", "score_date", name="uq_genre_score_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    genre = Column(String(100), nullable=False, index=True)
    score_date = Column(Date, nullable=False, index=True)

    # Core scores (0-100)
    hotness_score = Column(Integer)
    saturation_score = Column(Integer)
    success_rate_score = Column(Integer)
    timing_score = Column(Integer)

    # Overall
    overall_score = Column(Integer)
    recommendation = Column(Text)  # 'hot', 'growing', 'saturated', 'declining'

    # Enhanced: Velocity & trend (new columns)
    growth_velocity = Column(Integer)  # Week-over-week CCU change %
    competition_score = Column(Integer)  # 0-100, based on releases + saturation
    revenue_potential_score = Column(Integer)  # Based on avg price * success rate
    discoverability_score = Column(Integer)  # Based on median review count
    trend_direction = Column(String(20))  # 'rising', 'stable', 'declining'

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
