"""Base collector class."""
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectionRun

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Base class for data collectors."""

    name: str = "base"
    rate_limit_delay: float = 1.0  # Seconds between requests

    def __init__(self, session: AsyncSession):
        self.db = session
        self.client = httpx.AsyncClient(timeout=30.0)
        self.run_id: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def start_run(self) -> CollectionRun:
        """Record the start of a collection run."""
        run = CollectionRun(
            collector_name=self.name,
            started_at=datetime.utcnow(),
            status="running",
        )
        self.db.add(run)
        await self.db.flush()
        self.run_id = str(run.id)
        logger.info(f"Started collection run: {self.name} ({self.run_id})")
        return run

    async def complete_run(self, records: int, error: str | None = None):
        """Record the completion of a collection run."""
        from sqlalchemy import update

        status = "failed" if error else "completed"
        await self.db.execute(
            update(CollectionRun)
            .where(CollectionRun.id == self.run_id)
            .values(
                completed_at=datetime.utcnow(),
                status=status,
                records_processed=records,
                error_message=error,
            )
        )
        logger.info(f"Completed collection run: {self.name} - {status} ({records} records)")

    @abstractmethod
    async def collect(self) -> int:
        """Run the collection. Returns number of records processed."""
        pass

    async def fetch_json(self, url: str, **kwargs) -> dict[str, Any] | None:
        """Fetch JSON from URL with error handling."""
        try:
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
