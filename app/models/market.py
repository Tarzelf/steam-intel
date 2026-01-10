"""Market intelligence models."""
import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, Integer, Date, DateTime, ARRAY, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.database import Base


class GenreSnapshot(Base):
    """Genre/tag trend snapshot."""

    __tablename__ = "genre_snapshots"
    __table_args__ = (
        UniqueConstraint("genre", "snapshot_date", name="uq_genre_snapshot_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    genre = Column(String(100), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)

    # Metrics
    game_count = Column(Integer)
    total_ccu = Column(Integer)
    avg_ccu = Column(Integer)
    total_owners_estimate = Column(Integer)
    avg_review_score = Column(Integer)

    # Top games in this genre
    top_games = Column(JSONB)  # [{app_id, name, ccu, owners}]

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
