"""Market intelligence models."""
import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, Integer, Date, DateTime, ARRAY, Float, Boolean, BigInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class GenreSnapshot(Base):
    """Genre/tag trend snapshot with enhanced metrics."""

    __tablename__ = "genre_snapshots"
    __table_args__ = (
        UniqueConstraint("genre", "snapshot_date", name="uq_genre_snapshot_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    genre = Column(String(100), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)

    # Core metrics
    game_count = Column(Integer)
    total_ccu = Column(Integer)
    avg_ccu = Column(Integer)
    total_owners_estimate = Column(Integer)
    avg_review_score = Column(Integer)

    # Top games in this genre
    top_games = Column(JSONB)  # [{app_id, name, ccu, owners}]

    # Enhanced: Pricing analytics
    avg_price_cents = Column(Integer)
    median_price_cents = Column(Integer)
    price_distribution = Column(JSONB)  # {free, under_5, 5_to_10, 10_to_20, 20_to_30, over_30}

    # Enhanced: Release velocity
    releases_last_30d = Column(Integer)
    releases_last_90d = Column(Integer)

    # Enhanced: Early Access analysis
    early_access_count = Column(Integer)
    early_access_pct = Column(Integer)

    # Enhanced: Visibility & age
    median_review_count = Column(Integer)
    avg_game_age_days = Column(Integer)

    # Enhanced: Tag co-occurrence
    top_tags = Column(JSONB)  # [{tag, count}]

    # Enhanced: Revenue estimate
    revenue_estimate_cents = Column(BigInteger)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TopSellersSnapshot(Base):
    """Top sellers snapshot."""

    __tablename__ = "top_sellers_snapshots"
    __table_args__ = (
        UniqueConstraint("category", "snapshot_date", name="uq_topsellers_snapshot_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_date = Column(Date, nullable=False, index=True)
    category = Column(String(50), nullable=False)  # 'global', 'indie', etc.

    # Rankings
    rankings = Column(JSONB, nullable=False)  # [{rank, app_id, name, price}]

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class NewRelease(Base):
    """New release tracking."""

    __tablename__ = "new_releases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    release_date = Column(Date, nullable=False)
    genres = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    price_cents = Column(Integer)

    # First week performance
    week1_ccu = Column(Integer)
    week1_reviews = Column(Integer)
    week1_review_score = Column(Integer)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class GenreGame(Base):
    """Individual game data per genre snapshot for detailed analysis."""

    __tablename__ = "genre_games"
    __table_args__ = (
        UniqueConstraint("genre", "app_id", "snapshot_date", name="uq_genre_game_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    genre = Column(String(100), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    app_id = Column(Integer, nullable=False)
    name = Column(String(255))

    # Metrics
    ccu = Column(Integer)
    owners_min = Column(Integer)
    owners_max = Column(Integer)
    reviews_positive = Column(Integer)
    reviews_negative = Column(Integer)
    review_score = Column(Integer)
    price_cents = Column(Integer)
    discount_percent = Column(Integer)
    release_date = Column(Date)
    is_early_access = Column(Boolean, default=False)
    tags = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TagCorrelation(Base):
    """Tag co-occurrence analysis for identifying synergistic combinations."""

    __tablename__ = "tag_correlations"
    __table_args__ = (
        UniqueConstraint("tag_a", "tag_b", "snapshot_date", name="uq_tag_correlation_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_a = Column(String(100), nullable=False)
    tag_b = Column(String(100), nullable=False)
    snapshot_date = Column(Date, nullable=False, index=True)

    co_occurrence_count = Column(Integer)
    correlation_strength = Column(Float)
    combined_ccu = Column(Integer)
    avg_review_score = Column(Integer)
    avg_price_cents = Column(Integer)
    top_games = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class MarketTrend(Base):
    """Weekly market trend aggregates for trend analysis."""

    __tablename__ = "market_trends"
    __table_args__ = (
        UniqueConstraint("week_start", "genre", name="uq_market_trend_week"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    week_start = Column(Date, nullable=False)
    genre = Column(String(100), nullable=False, index=True)

    # Weekly metrics
    total_ccu = Column(Integer)
    game_count = Column(Integer)
    new_releases = Column(Integer)
    avg_review_score = Column(Integer)
    avg_price_cents = Column(Integer)

    # Week-over-week changes
    ccu_change_pct = Column(Float)
    game_count_change_pct = Column(Float)

    # Computed trend
    trend_score = Column(Integer)  # -100 to +100
    trend_label = Column(String(20))  # surging, growing, stable, declining, crashing

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class UpcomingRelease(Base):
    """Upcoming releases for competitive intelligence."""

    __tablename__ = "upcoming_releases"
    __table_args__ = (
        UniqueConstraint("app_id", name="uq_upcoming_app"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    developer = Column(String(255))
    publisher = Column(String(255))
    expected_release = Column(Date)
    genres = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    price_cents = Column(Integer)
    has_demo = Column(Boolean, default=False)
    wishlist_estimate = Column(Integer)
    hype_score = Column(Integer)
    source = Column(String(50))

    last_updated = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
