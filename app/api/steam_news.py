"""Steam News API - Proxy for Steam news with caching."""
import logging
from typing import Optional

import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Request

from app.api.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/steam", tags=["steam"])

# 5-minute cache for news requests
news_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


@router.get("/news/{app_id}")
async def get_steam_news(
    app_id: int,
    request: Request,
    count: int = 10,
):
    """
    Fetch Steam news for an app with caching.

    Proxies the Steam Web API to avoid CORS issues in the browser.
    Results are cached for 5 minutes to reduce API calls.

    Args:
        app_id: Steam App ID
        count: Number of news items to fetch (default 10, max 100)

    Returns:
        Steam news API response
    """
    # Verify API key
    await verify_api_key(request.headers.get("X-API-Key"))

    # Validate count
    count = min(max(1, count), 100)

    # Check cache
    cache_key = f"{app_id}:{count}"
    if cache_key in news_cache:
        logger.debug(f"Cache hit for Steam news app_id={app_id}")
        return news_cache[cache_key]

    # Fetch from Steam API
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    params = {
        "appid": app_id,
        "count": count,
        "maxlength": 0,  # Get full content
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        # Cache the result
        news_cache[cache_key] = data
        logger.info(f"Fetched Steam news for app_id={app_id}, count={len(data.get('appnews', {}).get('newsitems', []))}")

        return data

    except httpx.TimeoutException:
        logger.error(f"Timeout fetching Steam news for app_id={app_id}")
        raise HTTPException(status_code=504, detail="Steam API timeout")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching Steam news: {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Steam API error: {e.response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching Steam news for app_id={app_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch Steam news")
