from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from ..models import SiteConfig


class FinnhubError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, code: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass
class Quote:
    symbol: str
    c: Optional[float] = None  # current price
    pc: Optional[float] = None  # previous close
    h: Optional[float] = None
    l: Optional[float] = None
    dp: Optional[float] = None  # percent change
    d: Optional[float] = None   # change
    t: Optional[int] = None     # timestamp (unix)
    pre: Optional[float] = None  # pre-market (if available)
    post: Optional[float] = None  # post-market (if available)


class FinnhubClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        backoff_factor: Optional[float] = None,
    ):
        db_key = None
        try:
            cfg = SiteConfig.objects.first()
            if cfg and cfg.finnhub_api_key:
                db_key = cfg.finnhub_api_key.strip()
        except Exception:
            db_key = None
        self.api_key = api_key or db_key or settings.FINNHUB_API_KEY
        self.base_url = base_url or settings.FINNHUB_BASE_URL
        self.timeout = timeout or settings.FINNHUB_TIMEOUT_SECONDS
        self.max_retries = max_retries or settings.FINNHUB_MAX_RETRIES
        self.backoff_factor = backoff_factor or settings.FINNHUB_BACKOFF_FACTOR

    def _request(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise FinnhubError("Missing Finnhub API key", code="NO_API_KEY")

        # Always include token
        q = {"token": self.api_key}
        q.update(params)
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(q)}"

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "HeatmapApp/1.0"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.getcode()
                    raw = resp.read().decode("utf-8")
                    if status >= 400:
                        raise FinnhubError(f"HTTP {status}", status=status)
                    data = json.loads(raw or '{}')
                    return data
            except urllib.error.HTTPError as e:
                # Map known error statuses
                status = e.code
                if status == 401:
                    raise FinnhubError("Invalid API key", status=401, code="INVALID_KEY")
                if status == 429:
                    # rate limited; fall-through to retry with backoff
                    last_exc = FinnhubError("Rate limited", status=429, code="RATE_LIMIT")
                elif 500 <= status < 600:
                    last_exc = FinnhubError(f"Server error {status}", status=status, code="SERVER_ERROR")
                else:
                    raise FinnhubError(f"HTTP error {status}", status=status)
            except urllib.error.URLError as e:
                last_exc = FinnhubError(f"Network error: {e}", code="NETWORK")

            # Retry with exponential backoff
            delay = (self.backoff_factor) * (2 ** attempt)
            time.sleep(min(delay, 5))

        if last_exc:
            raise last_exc
        raise FinnhubError("Unknown error")

    # Public API methods
    def search(self, query: str, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"q": query}
        data = self._request("/search", params)
        results = data.get("result", [])
        # Filter to common stock-esque types and US by default if possible
        filtered: List[Dict[str, Any]] = []
        for r in results:
            typ = (r.get("type") or "").lower()
            mic = (r.get("mic") or r.get("primaryExchange") or "").upper()
            # heuristics for common stock and US MICs
            is_common = any(k in typ for k in ["common", "equity", "stock"]) or typ == "e" or typ == "cs"
            is_us = (mic in {"XNYS", "XNAS", "ARCX", "BATS", "IEXG", "FINN"}) or (exchange == "US")
            if is_common and (not exchange or is_us):
                filtered.append(r)
        return filtered

    def quote(self, symbol: str) -> Quote:
        data = self._request("/quote", {"symbol": symbol})
        q = Quote(
            symbol=symbol,
            c=data.get("c"),
            pc=data.get("pc"),
            h=data.get("h"),
            l=data.get("l"),
            dp=data.get("dp"),
            d=data.get("d"),
            t=data.get("t"),
        )
        # Finnhub quote endpoint does not explicitly include pre/post, keep None
        return q

    def profile(self, symbol: str) -> Dict[str, Any]:
        return self._request("/stock/profile2", {"symbol": symbol})

    def metrics(self, symbol: str) -> Dict[str, Any]:
        data = self._request("/stock/metric", {"symbol": symbol, "metric": "all"})
        metric = data.get("metric") or {}
        out = {
            "week52High": metric.get("52WeekHigh"),
            "week52Low": metric.get("52WeekLow"),
        }
        return out


def compute_us_market_status(now_ts: Optional[float] = None) -> Dict[str, Any]:
    """Compute a basic US market session status based on NY timezone.
    Sessions: Pre-market 04:00-09:30, Regular 09:30-16:00, Post-market 16:00-20:00, Closed otherwise.
    """
    from datetime import datetime, time as dtime
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
    except Exception:  # pragma: no cover - fallback if not available
        ZoneInfo = None

    tz = ZoneInfo("America/New_York") if ZoneInfo else None
    now = datetime.fromtimestamp(now_ts, tz) if (now_ts and tz) else datetime.now(tz)
    weekday = now.weekday()  # 0=Mon
    hhmm = now.time()

    pre_start = dtime(4, 0)
    regular_start = dtime(9, 30)
    regular_end = dtime(16, 0)
    post_end = dtime(20, 0)

    status = {
        "isOpen": False,
        "session": "Closed",
        "timestamp": int(now.timestamp()),
    }

    if weekday >= 5:  # Weekend
        return status

    if pre_start <= hhmm < regular_start:
        status.update({"session": "Pre-Market"})
    elif regular_start <= hhmm < regular_end:
        status.update({"isOpen": True, "session": "Regular"})
    elif regular_end <= hhmm < post_end:
        status.update({"session": "Post-Market"})
    else:
        status.update({"session": "Closed"})

    return status
