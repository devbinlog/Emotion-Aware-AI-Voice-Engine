"""
Web search utilities — no API key required.

Weather : Open-Meteo API  (free, no key, real-time)
General : DuckDuckGo Instant Answer API (free, no key)
"""
from __future__ import annotations

import re
from typing import Optional

import httpx

from app.utils.logging import logger

# ── Weather ───────────────────────────────────────────────────────────────────

_WEATHER_KW = re.compile(
    r"날씨|기온|온도|비|눈|흐|맑|weather|temperature|forecast|rain|snow|humid|sunny|cloudy",
    re.IGNORECASE,
)

# Korean city → (lat, lon, display name)
_CITY_COORDS = {
    "서울":  (37.5665, 126.9780, "서울"),
    "부산":  (35.1796, 129.0756, "부산"),
    "인천":  (37.4563, 126.7052, "인천"),
    "대구":  (35.8714, 128.6014, "대구"),
    "광주":  (35.1595, 126.8526, "광주"),
    "대전":  (36.3504, 127.3845, "대전"),
    "울산":  (35.5384, 129.3114, "울산"),
    "제주":  (33.4996, 126.5312, "제주"),
    "수원":  (37.2636, 127.0286, "수원"),
    "전주":  (35.8242, 127.1480, "전주"),
    "청주":  (36.6424, 127.4890, "청주"),
    "seoul": (37.5665, 126.9780, "서울"),
    "busan": (35.1796, 129.0756, "부산"),
    "jeju":  (33.4996, 126.5312, "제주"),
}

_CITY_RE = re.compile("|".join(_CITY_COORDS.keys()), re.IGNORECASE)

_WMO_CODE = {
    0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림",
    45: "안개", 48: "안개",
    51: "이슬비", 53: "이슬비", 55: "이슬비",
    61: "비", 63: "비", 65: "폭우",
    71: "눈", 73: "눈", 75: "폭설",
    80: "소나기", 81: "소나기", 82: "폭우",
    95: "천둥번개",
}


async def fetch_weather(query: str) -> Optional[str]:
    """Return a Korean weather summary for the city mentioned in query."""
    match = _CITY_RE.search(query)
    city_key = match.group(0).lower() if match else "서울"
    lat, lon, city_name = _CITY_COORDS.get(city_key, _CITY_COORDS["서울"])

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weathercode,windspeed_10m,relativehumidity_2m"
        f"&timezone=Asia%2FSeoul"
    )
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()["current"]
                temp = data["temperature_2m"]
                code = data["weathercode"]
                wind = data["windspeed_10m"]
                hum  = data["relativehumidity_2m"]
                desc = _WMO_CODE.get(code, "알 수 없음")
                result = (
                    f"{city_name} 현재 날씨: {desc}, "
                    f"기온 {temp}°C, 습도 {hum}%, 바람 {wind}km/h"
                )
                logger.info(f"Web: weather fetched — {result}")
                return result
    except Exception as e:
        logger.debug(f"Web: weather fetch failed — {e}")
    return None


# ── DuckDuckGo Instant Answer ─────────────────────────────────────────────────

async def fetch_ddg(query: str) -> Optional[str]:
    """Fetch a DuckDuckGo Instant Answer abstract for the query."""
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            )
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("AbstractText", "").strip()
                if abstract:
                    logger.info(f"Web: DDG answer fetched ({len(abstract)} chars)")
                    return abstract[:400]
    except Exception as e:
        logger.debug(f"Web: DDG fetch failed — {e}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def search_if_needed(query: str) -> Optional[str]:
    """
    Returns a search result string to inject into LLM context if the query
    needs real-time info, otherwise returns None.
    Only triggers for weather queries — general DDG search is disabled to
    avoid polluting emotional/casual conversation context.
    """
    if _WEATHER_KW.search(query):
        result = await fetch_weather(query)
        if result:
            return f"[실시간 날씨] {result}"

    return None
