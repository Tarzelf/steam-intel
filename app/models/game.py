"""Game and snapshot models."""
import uuid
from datetime import date, datetime
from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, ForeignKey, ARRAY, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Game(Base):
    """A game being tracked."""

    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    app_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    developer = Column(String(255))
    publisher = Column(String(255))
    release_date = Column(Date)
    price_cents = Column(Integer)
    genres = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    is_portfolio = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    snapshots = relationship("GameSnapshot", back_populates="game", cascade="all, delete-orphan")


class GameSnapshot(Base):
    """Point-in-time stats for a game."""

    __tablename__ = "game_snapshots"
    __table_args__ = (
        UniqueConstraint("app_id", "snapshot_date", name="uq_game_snapshot_date"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    app_id = Column(Integer, nullable=False, index=True)

    # Ownership & Players
    owners_min = Column(Integer)
    owners_max = Column(Integer)
    ccu = Column(Integer)
    players_2weeks = Column(Integer)

    # Playtime
    avg_playtime_minutes = Column(Integer)
    median_playtime_minutes = Column(Integer)
    avg_playtime_2weeks_minutes = Column(Integer)

    # Reviews
    reviews_positive = Column(Integer)
    reviews_negative = Column(Integer)
    review_score = Column(Integer)

    # Pricing
    price_cents = Column(Integer)
    discount_percent = Column(Integer)

    # Metadata
    snapshot_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    game = relationship("Game", back_populates="snapshots")
