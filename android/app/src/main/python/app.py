from __future__ import annotations

import html
import math
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS


def resource_path(relative_path: str) -> str:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base_path / relative_path)


app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
CORS(app)

NASDAQ_MIN_MARKET_CAP = 10_000_000_000
DEFAULT_SCAN_LIMIT = 500
MAX_SCAN_LIMIT = 500
FALLBACK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AVGO", "COST", "NFLX"]
CHINA_RELATED_COUNTRIES = {"china", "hong kong", "macau", "macao"}
CHINA_RELATED_NAME_PATTERNS = [
    "china",
    "chinese",
    "hong kong",
    "macau",
    "macao",
    "cayman islands",
]

HALVINGS = [
    date(2012, 11, 28),
    date(2016, 7, 9),
    date(2020, 5, 11),
    date(2024, 4, 20),
]
ESTIMATED_NEXT_HALVING = date(2028, 4, 20)
NEXT_HALVING_BLOCK = 1_050_000
BITCOIN_AVERAGE_BLOCK_SECONDS = 10 * 60
FEAR_GREED_ZH = {
    "extreme fear": "极度恐慌",
    "fear": "恐慌",
    "neutral": "中性",
    "greed": "贪婪",
    "extreme greed": "极度贪婪",
}
VIX_BANDS = [
    {"key": "quiet", "label": "低波动/贪婪", "range": "<13", "min": 0.0, "max": 13.0},
    {"key": "normal", "label": "常态波动", "range": "13-18", "min": 13.0, "max": 18.0},
    {"key": "watch", "label": "压力观察", "range": "18-24", "min": 18.0, "max": 24.0},
    {"key": "fear", "label": "恐慌买入区", "range": "24-30", "min": 24.0, "max": 30.0},
    {"key": "panic", "label": "极端恐慌", "range": ">=30", "min": 30.0, "max": float("inf")},
]
BTC_HALVING_CYCLE_TURNS = [
    {"cycle": "2012-2015", "halving": date(2012, 11, 28), "top": date(2013, 12, 4), "bottom": date(2015, 1, 14)},
    {"cycle": "2016-2018", "halving": date(2016, 7, 9), "top": date(2017, 12, 17), "bottom": date(2018, 12, 15)},
    {"cycle": "2020-2022", "halving": date(2020, 5, 11), "top": date(2021, 11, 10), "bottom": date(2022, 11, 21)},
]
BTC_TOP_TO_BOTTOM_TURNS = [
    {"cycle": "2013-2015", "top": date(2013, 12, 4), "bottom": date(2015, 1, 14)},
    {"cycle": "2017-2018", "top": date(2017, 12, 17), "bottom": date(2018, 12, 15)},
    {"cycle": "2021-2022", "top": date(2021, 11, 10), "bottom": date(2022, 11, 21)},
]
BTC_BOTTOM_TO_TOP_TURNS = [
    {"cycle": "2015-2017", "bottom": date(2015, 1, 14), "top": date(2017, 12, 17)},
    {"cycle": "2018-2021", "bottom": date(2018, 12, 15), "top": date(2021, 11, 10)},
]
BTC_CURRENT_CYCLE_BOTTOM = date(2022, 11, 21)

CACHE_SECONDS = 55
UNIVERSE_CACHE_SECONDS = 10 * 60
TARGET_CACHE_SECONDS = 60 * 60
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
NASDAQ_HEADERS = {
    **HEADERS,
    "Accept": "application/json,text/plain,*/*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
}
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str, ttl_seconds: int = CACHE_SECONDS) -> Any | None:
    item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if time.time() - ts > ttl_seconds:
        return None
    return value


def _cache_set(key: str, value: Any) -> Any:
    _cache[key] = (time.time(), value)
    return value


def clean_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").replace("%", "").strip()
        if value == "":
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def clean_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def yahoo_chart(symbol: str, range_: str = "1y", interval: str = "1d") -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = requests.get(
        url,
        params={"range": range_, "interval": interval, "includePrePost": "true"},
        headers=HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    error = data.get("chart", {}).get("error")
    if error:
        raise ValueError(error.get("description") or str(error))
    result = data.get("chart", {}).get("result") or []
    if not result:
        raise ValueError(f"{symbol} chart unavailable")
    return result[0]


def extract_closes(chart: dict[str, Any]) -> list[float]:
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    return [float(item) for item in closes if item is not None]


def extract_daily_points(chart: dict[str, Any]) -> list[dict[str, Any]]:
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    timestamps = chart.get("timestamp") or []
    points = []
    for timestamp, close in zip(timestamps, closes):
        value = clean_float(close)
        if value is None:
            continue
        day = datetime.fromtimestamp(int(timestamp), timezone.utc).date()
        points.append({"date": day, "close": value})
    return points


def timestamp_to_iso(timestamp: Any) -> str | None:
    value = clean_int(timestamp, 0)
    if not value:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return statistics.fmean(values[-window:])


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = deltas[-period:]
    gains = [max(delta, 0) for delta in recent]
    losses = [abs(min(delta, 0)) for delta in recent]
    avg_gain = statistics.fmean(gains)
    avg_loss = statistics.fmean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_nasdaq_large_caps(min_market_cap: float = NASDAQ_MIN_MARKET_CAP) -> dict[str, Any]:
    min_market_cap = max(0, min_market_cap)
    cache_key = f"nasdaq_large_caps:{round(min_market_cap)}"
    cached = _cache_get(cache_key, UNIVERSE_CACHE_SECONDS)
    if cached:
        return cached

    response = requests.get(
        "https://api.nasdaq.com/api/screener/stocks",
        params={"tableonly": "true", "limit": "25", "offset": "0", "exchange": "NASDAQ", "download": "true"},
        headers=NASDAQ_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json().get("data", {}).get("rows") or []
    if not rows:
        raise ValueError("NASDAQ large-cap universe is empty")
    large_caps: list[dict[str, Any]] = []
    excluded_china_related = 0

    for row in rows:
        if is_china_related_listing(row):
            excluded_china_related += 1
            continue
        market_cap = clean_float(row.get("marketCap"))
        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol or not market_cap or market_cap < min_market_cap:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
            continue
        large_caps.append(
            {
                "symbol": symbol,
                "name": row.get("name") or symbol,
                "price": clean_float(row.get("lastsale")),
                "changePct": clean_float(row.get("pctchange")),
                "volume": clean_float(row.get("volume")),
                "marketCap": market_cap,
                "country": row.get("country") or "",
                "sector": row.get("sector") or "N/A",
                "industry": row.get("industry") or "N/A",
                "sourceUrl": "https://www.nasdaq.com" + row.get("url", ""),
            }
        )

    large_caps.sort(key=lambda item: item["marketCap"], reverse=True)
    large_caps_payload = {
        "rows": large_caps,
        "excludedChinaRelated": excluded_china_related,
        "minMarketCap": min_market_cap,
        "rawCount": len(rows),
    }
    return _cache_set(cache_key, large_caps_payload)


def is_china_related_listing(row: dict[str, Any]) -> bool:
    country = (row.get("country") or "").strip().lower()
    name = (row.get("name") or "").strip().lower()
    if country in CHINA_RELATED_COUNTRIES:
        return True
    if ("american depositary" in name or " adr" in name or " ads" in name) and any(
        pattern in name for pattern in CHINA_RELATED_NAME_PATTERNS
    ):
        return True
    return False


def infer_consensus_rating(buy: int, hold: int, sell: int) -> str | None:
    if buy == hold == sell == 0:
        return None
    if buy >= hold * 1.4 and buy > sell:
        return "Buy"
    if sell > buy and sell >= hold:
        return "Sell"
    return "Hold"


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def parse_us_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def rating_rank(value: str | None) -> int:
    normalized = (value or "").strip().lower()
    if normalized in {"strong buy", "outperform", "overweight"}:
        return 3
    if normalized == "buy":
        return 2
    if normalized in {"hold", "neutral", "market perform"}:
        return 1
    if normalized in {"sell", "underperform", "underweight"}:
        return 0
    return 1


def infer_rating_action(current: str | None, previous: str | None) -> str:
    if not current or not previous:
        return "Maintains"
    current_rank = rating_rank(current)
    previous_rank = rating_rank(previous)
    if current_rank > previous_rank:
        return "Upgrades"
    if current_rank < previous_rank:
        return "Downgrades"
    return "Maintains"


def infer_price_action(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "Maintains"
    if current > previous:
        return "Raises"
    if current < previous:
        return "Lowers"
    return "Maintains"


def fetch_nasdaq_target_price(symbol: str) -> dict[str, Any]:
    url_symbol = symbol.lower().replace(".", "-")
    response = requests.get(
        f"https://api.nasdaq.com/api/analyst/{url_symbol}/targetprice",
        headers={
            **NASDAQ_HEADERS,
            "Referer": f"https://www.nasdaq.com/market-activity/stocks/{url_symbol}/analyst-research",
        },
        timeout=12,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    overview = data.get("consensusOverview") or {}
    price_target = clean_float(overview.get("priceTarget"))
    low = clean_float(overview.get("lowPriceTarget"))
    high = clean_float(overview.get("highPriceTarget"))
    buy = int(clean_float(overview.get("buy"), 0) or 0)
    hold = int(clean_float(overview.get("hold"), 0) or 0)
    sell = int(clean_float(overview.get("sell"), 0) or 0)
    analyst_count = buy + hold + sell

    historical = data.get("historicalConsensus") or []
    consensus_rating = None
    historical_recommendations: list[dict[str, Any]] = []
    previous_point: dict[str, Any] | None = None
    latest_point: dict[str, Any] | None = None
    for item in reversed(historical):
        z_value = item.get("z") or {}
        if z_value.get("consensus"):
            consensus_rating = z_value["consensus"]
            break
    for item in historical:
        z_value = item.get("z") or {}
        point_date = parse_us_date(z_value.get("date"))
        historical_recommendations.append(
            {
                "date": point_date.isoformat() if point_date else z_value.get("date"),
                "month": point_date.strftime("%b") if point_date else z_value.get("date"),
                "buy": int(clean_float(z_value.get("buy"), 0) or 0),
                "hold": int(clean_float(z_value.get("hold"), 0) or 0),
                "sell": int(clean_float(z_value.get("sell"), 0) or 0),
                "consensus": z_value.get("consensus"),
                "priceTarget": clean_float(item.get("y")),
            }
        )
    if len(historical_recommendations) >= 2:
        previous_point = historical_recommendations[-2]
        latest_point = historical_recommendations[-1]
    elif historical_recommendations:
        latest_point = historical_recommendations[-1]
    consensus_rating = consensus_rating or infer_consensus_rating(buy, hold, sell)

    if not price_target and not low and not high:
        return {"sourceAvailable": False}

    return {
        "sourceAvailable": True,
        "sourceName": "NASDAQ Analyst Research",
        "sourceUrl": f"https://www.nasdaq.com/market-activity/stocks/{url_symbol}/analyst-research",
        "targetLowPrice": low,
        "targetMeanPrice": price_target,
        "targetMedianPrice": None,
        "targetHighPrice": high,
        "analystOpinions": analyst_count or None,
        "consensusRating": consensus_rating,
        "recommendationBreakdown": {"buy": buy, "hold": hold, "sell": sell},
        "historicalRecommendations": historical_recommendations[-6:],
        "latestConsensus": {
            "date": latest_point.get("date") if latest_point else None,
            "analyst": "NASDAQ Consensus",
            "ratingAction": infer_rating_action(
                latest_point.get("consensus") if latest_point else consensus_rating,
                previous_point.get("consensus") if previous_point else None,
            ),
            "rating": latest_point.get("consensus") if latest_point else consensus_rating,
            "priceAction": infer_price_action(
                latest_point.get("priceTarget") if latest_point else price_target,
                previous_point.get("priceTarget") if previous_point else None,
            ),
            "priceTarget": price_target,
            "previousPriceTarget": previous_point.get("priceTarget") if previous_point else None,
        },
    }


def fetch_nasdaq_ratings(symbol: str) -> dict[str, Any]:
    url_symbol = symbol.lower().replace(".", "-")
    response = requests.get(
        f"https://api.nasdaq.com/api/analyst/{url_symbol}/ratings",
        headers={
            **NASDAQ_HEADERS,
            "Referer": f"https://www.nasdaq.com/market-activity/stocks/{url_symbol}/analyst-research",
        },
        timeout=12,
    )
    response.raise_for_status()
    data = response.json().get("data") or {}
    return {
        "meanRatingType": data.get("meanRatingType"),
        "ratingsSummary": data.get("ratingsSummary"),
        "brokerNames": data.get("brokerNames") or [],
        "upgradesDowngrades": data.get("upgradesDowngrades") or [],
    }


def fetch_stockanalysis_rating_details(symbol: str) -> dict[str, Any]:
    if "." in symbol:
        return {}
    url_symbol = symbol.lower().replace("-", ".")
    url = f"https://stockanalysis.com/stocks/{url_symbol}/ratings/"
    response = requests.get(url, headers=HEADERS, timeout=10)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    text = html.unescape(response.text)
    rows: list[dict[str, Any]] = []
    for match in re.finditer(r"<tr[^>]*>(.*?)</tr>", text, re.IGNORECASE | re.DOTALL):
        row_html = match.group(1)
        if "analyst-name" not in row_html:
            continue
        cells = [strip_html(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.IGNORECASE | re.DOTALL)]
        if len(cells) < 8:
            continue
        analyst_match = re.search(r'<div class="analyst-name[^>]*" title="([^"]+)"', row_html)
        stars_match = re.search(r"--rating:\s*([\d.]+)", row_html)
        analyst = analyst_match.group(1) if analyst_match else cells[0]
        firm = cells[1]
        rating = cells[3]
        action = cells[4]
        price_target = clean_float(cells[5])
        upside_pct = clean_float(cells[6])
        rating_date = parse_us_date(cells[7])
        stars = clean_float(stars_match.group(1))
        rows.append(
            {
                "analyst": analyst,
                "firm": firm,
                "stars": stars,
                "score": round((stars or 0) * 20) if stars is not None else None,
                "rating": rating,
                "ratingAction": action,
                "priceTarget": price_target,
                "upsidePct": upside_pct,
                "date": rating_date.isoformat() if rating_date else cells[7],
            }
        )
    if not rows:
        return {"sourceUrl": url, "ratings": []}
    top_analyst = max(rows, key=lambda item: item.get("score") or 0)
    return {
        "sourceUrl": url,
        "topAnalyst": top_analyst,
        "latestRating": rows[0],
        "ratings": rows[:10],
    }


def fetch_stockanalysis_target_price(symbol: str) -> dict[str, Any]:
    if "." in symbol:
        return {"sourceAvailable": False}
    url_symbol = symbol.lower().replace("-", ".")
    url = f"https://stockanalysis.com/stocks/{url_symbol}/forecast/"
    response = requests.get(url, headers=HEADERS, timeout=10)
    if response.status_code == 404:
        return {"sourceAvailable": False, "sourceUrl": url}
    response.raise_for_status()
    text = html.unescape(response.text)

    table_match = re.search(
        r"<th[^>]*>Target</th>.*?<td[^>]*>Price</td>"
        r"\s*<td[^>]*>\$?([\d,.]+)</td>"
        r"\s*<td[^>]*>\$?([\d,.]+)</td>"
        r"\s*<td[^>]*>\$?([\d,.]+)</td>"
        r"\s*<td[^>]*>\$?([\d,.]+)</td>",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not table_match:
        return {"sourceAvailable": False, "sourceUrl": url}

    count = None
    consensus_rating = None
    stated_upside_pct = None
    summary_match = re.search(
        r"According to\s+(\d+)\s+analysts?\s+polled by S&P Global,.*?"
        r'consensus rating of\s+"([^"]+)".*?'
        r"average price target of\s+\$?([\d,.]+).*?"
        r"forecast is\s+([+-]?[\d,.]+)%",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if summary_match:
        count = int(summary_match.group(1))
        consensus_rating = summary_match.group(2)
        stated_upside_pct = clean_float(summary_match.group(4))

    count_patterns = [
        r"Based on\s+(\d+)\s+analysts?",
        r"(\d+)\s+analysts?\s+have",
        r"according to\s+(\d+)\s+stock analysts?",
    ]
    if count is None:
        for pattern in count_patterns:
            count_match = re.search(pattern, text, re.IGNORECASE)
            if count_match:
                count = int(count_match.group(1))
                break

    low, average, median, high = [clean_float(item) for item in table_match.groups()]
    return {
        "sourceAvailable": True,
        "sourceUrl": url,
        "targetLowPrice": low,
        "targetMeanPrice": average,
        "targetMedianPrice": median,
        "targetHighPrice": high,
        "analystOpinions": count,
        "consensusRating": consensus_rating,
        "statedUpsidePct": stated_upside_pct,
        "sourceName": "StockAnalysis",
        "recommendationBreakdown": None,
    }


def parse_target_table(symbol: str) -> dict[str, Any]:
    cache_key = f"target:nasdaq:{symbol}"
    cached = _cache_get(cache_key, TARGET_CACHE_SECONDS)
    if cached:
        return cached

    try:
        target_data = fetch_nasdaq_target_price(symbol)
        if target_data.get("sourceAvailable"):
            return _cache_set(cache_key, target_data)
    except Exception:
        pass

    return _cache_set(cache_key, {"sourceAvailable": False})


def analyst_detail(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    cache_key = f"analyst_detail:{symbol}"
    cached = _cache_get(cache_key, TARGET_CACHE_SECONDS)
    if cached:
        return cached

    target_data = parse_target_table(symbol)
    if not target_data.get("sourceAvailable"):
        try:
            target_data = fetch_stockanalysis_target_price(symbol)
        except Exception:
            pass
    try:
        nasdaq_ratings = fetch_nasdaq_ratings(symbol)
    except Exception:
        nasdaq_ratings = {}
    try:
        stockanalysis_ratings = fetch_stockanalysis_rating_details(symbol)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 429:
            stockanalysis_ratings = {"sourceError": "rate_limited"}
        else:
            stockanalysis_ratings = {}
    except Exception:
        stockanalysis_ratings = {}

    latest_consensus = target_data.get("latestConsensus") or {}
    latest_rating = stockanalysis_ratings.get("latestRating")
    if latest_rating:
        latest_rating = {
            **latest_rating,
            "priceAction": latest_rating.get("priceAction") or latest_consensus.get("priceAction"),
            "previousPriceTarget": latest_rating.get("previousPriceTarget")
            or latest_consensus.get("previousPriceTarget"),
        }
    else:
        latest_rating = {
        "date": latest_consensus.get("date"),
        "analyst": latest_consensus.get("analyst") or "NASDAQ Consensus",
        "firm": target_data.get("sourceName") or "NASDAQ",
        "ratingAction": latest_consensus.get("ratingAction"),
        "rating": latest_consensus.get("rating") or target_data.get("consensusRating"),
        "priceAction": latest_consensus.get("priceAction"),
        "priceTarget": latest_consensus.get("priceTarget") or target_data.get("targetMeanPrice"),
        "previousPriceTarget": latest_consensus.get("previousPriceTarget"),
        }

    broker_names = nasdaq_ratings.get("brokerNames") or []
    top_analyst = stockanalysis_ratings.get("topAnalyst")
    if not top_analyst:
        buy = (target_data.get("recommendationBreakdown") or {}).get("buy") or 0
        total = target_data.get("analystOpinions") or 0
        score = round((buy / total) * 100) if total else None
        top_analyst = {
            "analyst": broker_names[0] if broker_names else "NASDAQ Consensus",
            "firm": broker_names[0] if broker_names else target_data.get("sourceName") or "NASDAQ",
            "score": score,
            "rating": target_data.get("consensusRating") or nasdaq_ratings.get("meanRatingType"),
        }

    payload = {
        "symbol": symbol,
        "target": {
            "low": target_data.get("targetLowPrice"),
            "average": target_data.get("targetMeanPrice"),
            "median": target_data.get("targetMedianPrice"),
            "high": target_data.get("targetHighPrice"),
            "sourceName": target_data.get("sourceName"),
            "sourceUrl": target_data.get("sourceUrl"),
            "available": bool(target_data.get("sourceAvailable")),
        },
        "topAnalyst": top_analyst,
        "latestRating": latest_rating,
        "recommendationBreakdown": target_data.get("recommendationBreakdown"),
        "historicalRecommendations": target_data.get("historicalRecommendations") or [],
        "ratingsSummary": nasdaq_ratings.get("ratingsSummary"),
        "brokerNames": broker_names,
        "stockanalysisSourceUrl": stockanalysis_ratings.get("sourceUrl"),
        "sourceError": stockanalysis_ratings.get("sourceError"),
    }
    return _cache_set(cache_key, payload)


def score_stock(
    price: float,
    meta: dict[str, Any],
    target_data: dict[str, Any],
    closes: list[float],
) -> dict[str, Any]:
    target = target_data.get("targetMeanPrice") or target_data.get("targetMedianPrice")
    upside_pct = ((target / price) - 1) * 100 if target and price else None
    opinions = target_data.get("analystOpinions") or 0
    high_52w = clean_float(meta.get("fiftyTwoWeekHigh"))
    low_52w = clean_float(meta.get("fiftyTwoWeekLow"))
    volume = clean_float(meta.get("regularMarketVolume")) or clean_float(meta.get("volume"))
    market_cap = clean_float(meta.get("marketCap"))
    ma50 = moving_average(closes, 50)
    ma200 = moving_average(closes, 200)

    discount_52w_pct = None
    if high_52w and high_52w > price:
        discount_52w_pct = (1 - price / high_52w) * 100

    momentum_vs_ma200_pct = None
    if ma200:
        momentum_vs_ma200_pct = (price / ma200 - 1) * 100

    score = 0.0
    if upside_pct is not None:
        score += clamp(upside_pct, -30, 85) * 0.72
    if opinions:
        score += clamp(opinions, 0, 35) * 0.45
    if discount_52w_pct is not None:
        score += clamp(discount_52w_pct, 0, 45) * 0.28
    if momentum_vs_ma200_pct is not None:
        score += clamp(18 - abs(momentum_vs_ma200_pct), -12, 12) * 0.35
    if volume and volume > 1_000_000:
        score += 3
    if market_cap and market_cap >= 50_000_000_000:
        score += 2

    if target is None:
        score = min(score, 50)
    if upside_pct is not None and upside_pct < 0:
        score -= 12

    score = round(clamp(score, 0, 100), 1)
    if target is None:
        label = "缺目标价，仅观察"
    elif score >= 72 and (upside_pct or 0) >= 20:
        label = "明显低估候选"
    elif score >= 58 and (upside_pct or 0) >= 10:
        label = "偏低估"
    elif score >= 42:
        label = "合理观察"
    else:
        label = "估值吸引力弱"

    risks: list[str] = []
    if target is None:
        risks.append("目标价源不可用")
    if opinions and opinions < 5:
        risks.append("分析师覆盖少")
    if momentum_vs_ma200_pct is not None and momentum_vs_ma200_pct < -20:
        risks.append("弱势趋势")
    if upside_pct is not None and upside_pct < 5:
        risks.append("目标价上行空间不足")

    return {
        "score": score,
        "label": label,
        "targetPrice": target,
        "targetLowPrice": target_data.get("targetLowPrice"),
        "targetMeanPrice": target_data.get("targetMeanPrice"),
        "targetMedianPrice": target_data.get("targetMedianPrice"),
        "targetHighPrice": target_data.get("targetHighPrice"),
        "upsidePct": round(upside_pct, 2) if upside_pct is not None else None,
        "analystOpinions": opinions or None,
        "consensusRating": target_data.get("consensusRating"),
        "statedUpsidePct": target_data.get("statedUpsidePct"),
        "week52High": high_52w,
        "week52Low": low_52w,
        "discount52wPct": round(discount_52w_pct, 2) if discount_52w_pct is not None else None,
        "ma50": round(ma50, 2) if ma50 else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "momentumVsMa200Pct": round(momentum_vs_ma200_pct, 2) if momentum_vs_ma200_pct is not None else None,
        "risks": risks,
        "targetSourceUrl": target_data.get("sourceUrl"),
        "targetSourceName": target_data.get("sourceName"),
        "targetSourceAvailable": bool(target_data.get("sourceAvailable")),
        "recommendationBreakdown": target_data.get("recommendationBreakdown"),
    }


def fetch_stock(symbol: str, seed: dict[str, Any] | None = None, include_technicals: bool = True) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    seed = seed or {}
    meta: dict[str, Any] = {
        "marketCap": seed.get("marketCap"),
        "volume": seed.get("volume"),
    }
    closes: list[float] = []
    price = clean_float(seed.get("price"))

    if include_technicals or not price:
        chart = yahoo_chart(symbol, "1y", "1d")
        meta.update(chart.get("meta") or {})
        closes = extract_closes(chart)
        price = clean_float(meta.get("regularMarketPrice")) or (closes[-1] if closes else price)

    if not price:
        raise ValueError(f"{symbol} missing price")

    target_data = parse_target_table(symbol)
    scored = score_stock(price, meta, target_data, closes)
    return {
        "symbol": symbol,
        "name": seed.get("name") or meta.get("shortName") or meta.get("longName") or symbol,
        "sector": seed.get("sector") or meta.get("exchangeName") or "N/A",
        "industry": seed.get("industry") or meta.get("fullExchangeName") or "N/A",
        "price": round(price, 2),
        "currency": meta.get("currency") or "USD",
        "marketCap": clean_float(seed.get("marketCap")) or clean_float(meta.get("marketCap")),
        "volume": clean_float(seed.get("volume")) or clean_float(meta.get("regularMarketVolume")),
        "changePct": clean_float(seed.get("changePct")),
        "recommendation": "N/A",
        "recommendationMean": None,
        **scored,
    }


def stock_screener(
    symbols: list[str],
    seed_by_symbol: dict[str, dict[str, Any]] | None = None,
    universe_meta: dict[str, Any] | None = None,
    include_technicals: bool = True,
) -> dict[str, Any]:
    seed_by_symbol = seed_by_symbol or {}
    universe_meta = universe_meta or {}
    meta_cache_part = "|".join(
        f"{key}={universe_meta.get(key)}"
        for key in ("universe", "minMarketCap", "universeCount", "analyzedCount")
        if key in universe_meta
    )
    cache_key = "stocks:" + ",".join(symbols) + f":tech={include_technicals}:meta={meta_cache_part}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    worker_count = 8 if include_technicals else 16
    with ThreadPoolExecutor(max_workers=min(worker_count, max(1, len(symbols)))) as executor:
        futures = {
            executor.submit(fetch_stock, symbol, seed_by_symbol.get(symbol), include_technicals): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})

    rows.sort(key=lambda item: item.get("score") or 0, reverse=True)
    payload = {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": (
            "数据源：NASDAQ 股票筛选器、NASDAQ 机构研究目标价、StockAnalysis 按需评级详情；启用技术指标时使用 Yahoo Finance 图表数据。"
        ),
        "symbols": symbols,
        "count": len(rows),
        "rows": rows,
        "errors": errors,
        **universe_meta,
    }
    return _cache_set(cache_key, payload)


def get_btc_spot() -> dict[str, Any]:
    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": "bitcoin",
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        },
        headers=HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()["bitcoin"]
    return {
        "price": clean_float(data.get("usd")),
        "marketCap": clean_float(data.get("usd_market_cap")),
        "volume24h": clean_float(data.get("usd_24h_vol")),
        "change24hPct": clean_float(data.get("usd_24h_change")),
        "lastUpdatedAt": data.get("last_updated_at"),
    }


def fear_greed_label_zh(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace("_", " ")
    return FEAR_GREED_ZH.get(normalized, value or "--")


def fear_greed_rating_from_score(score: float | None) -> tuple[str, str]:
    if score is None:
        return "--", "--"
    if score <= 24:
        label = "Extreme Fear"
    elif score <= 44:
        label = "Fear"
    elif score <= 55:
        label = "Neutral"
    elif score <= 75:
        label = "Greed"
    else:
        label = "Extreme Greed"
    return label, fear_greed_label_zh(label)


def get_crypto_fear_greed() -> dict[str, Any]:
    cached = _cache_get("crypto_fng", 5 * 60)
    if cached:
        return cached

    response = requests.get(
        "https://api.alternative.me/fng/",
        params={"limit": 1, "format": "json"},
        headers=HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    row = (response.json().get("data") or [{}])[0]
    value = clean_float(row.get("value"))
    classification = row.get("value_classification")
    payload = {
        "value": round(value) if value is not None else None,
        "classification": classification,
        "classificationZh": fear_greed_label_zh(classification),
        "timestamp": timestamp_to_iso(row.get("timestamp")),
        "timeUntilUpdateSeconds": clean_int(row.get("time_until_update"), 0) or None,
        "sourceName": "Alternative.me Crypto Fear & Greed Index",
        "sourceUrl": "https://alternative.me/crypto/fear-and-greed-index/",
    }
    return _cache_set("crypto_fng", payload)


def get_cnn_fear_greed() -> dict[str, Any]:
    cached = _cache_get("cnn_fng", 5 * 60)
    if cached:
        return cached

    response = requests.get(
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        headers={
            **HEADERS,
            "Accept": "application/json,text/plain,*/*",
            "Origin": "https://www.cnn.com",
            "Referer": "https://www.cnn.com/markets/fear-and-greed",
        },
        timeout=12,
    )
    response.raise_for_status()
    data = response.json().get("fear_and_greed") or {}
    score = clean_float(data.get("score"))
    rating = data.get("rating")
    payload = {
        "score": round(score, 1) if score is not None else None,
        "rating": rating,
        "ratingZh": fear_greed_label_zh(rating),
        "timestamp": data.get("timestamp"),
        "previousClose": clean_float(data.get("previous_close")),
        "previousWeek": clean_float(data.get("previous_1_week")),
        "previousMonth": clean_float(data.get("previous_1_month")),
        "sourceName": "CNN Fear & Greed Index",
        "sourceUrl": "https://www.cnn.com/markets/fear-and-greed",
    }
    return _cache_set("cnn_fng", payload)


def vix_band(value: float | None) -> dict[str, Any] | None:
    if value is None:
        return None
    for band in VIX_BANDS:
        if band["min"] <= value < band["max"]:
            return band
    return VIX_BANDS[-1]


def _return_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"sampleCount": 0, "positivePct": None, "avgReturnPct": None}
    positives = sum(1 for value in values if value > 0)
    return {
        "sampleCount": len(values),
        "positivePct": round(positives / len(values) * 100, 1),
        "avgReturnPct": round(statistics.fmean(values) * 100, 2),
    }


def _vix_probability_recommendation(band: dict[str, Any], row: dict[str, Any]) -> str:
    three_month = row.get("threeMonth") or {}
    six_month = row.get("sixMonth") or {}
    prob_3m = three_month.get("positivePct") or 0
    avg_3m = three_month.get("avgReturnPct") or 0
    prob_6m = six_month.get("positivePct") or 0
    avg_6m = six_month.get("avgReturnPct") or 0

    if band["key"] in {"panic", "fear"} and prob_6m >= 60 and avg_6m > 2:
        return "分批买入"
    if band["key"] == "watch" and prob_3m >= 55 and avg_3m > 1:
        return "小仓分批"
    if band["key"] == "quiet":
        return "高位防追高"
    if prob_3m < 52 and avg_3m < 1:
        return "降低仓位"
    return "持有观察"


def vix_probability_table(vix_points: list[dict[str, Any]], spy_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vix_by_date = {point["date"]: point["close"] for point in vix_points}
    spy_by_date = {point["date"]: point["close"] for point in spy_points}
    dates = sorted(set(vix_by_date).intersection(spy_by_date))
    buckets: dict[str, dict[str, Any]] = {
        band["key"]: {"band": band, "oneMonth": [], "threeMonth": [], "sixMonth": []}
        for band in VIX_BANDS
    }
    horizons = {"oneMonth": 21, "threeMonth": 63, "sixMonth": 126}

    for index, day in enumerate(dates):
        band = vix_band(vix_by_date.get(day))
        if not band:
            continue
        bucket = buckets[band["key"]]
        spot = spy_by_date.get(day)
        if not spot:
            continue
        for key, offset in horizons.items():
            if index + offset >= len(dates):
                continue
            future = spy_by_date.get(dates[index + offset])
            if future:
                bucket[key].append((future / spot) - 1)

    rows = []
    for band in VIX_BANDS:
        bucket = buckets[band["key"]]
        row = {
            "key": band["key"],
            "range": band["range"],
            "label": band["label"],
            "sampleCount": len(bucket["oneMonth"]),
            "oneMonth": _return_stats(bucket["oneMonth"]),
            "threeMonth": _return_stats(bucket["threeMonth"]),
            "sixMonth": _return_stats(bucket["sixMonth"]),
        }
        row["recommendation"] = _vix_probability_recommendation(band, row)
        rows.append(row)
    return rows


def market_sentiment() -> dict[str, Any]:
    cached = _cache_get("market_sentiment", 3 * 60)
    if cached:
        return cached

    vix_chart = yahoo_chart("^VIX", "10y", "1d")
    spy_chart = yahoo_chart("SPY", "10y", "1d")
    vix_points = extract_daily_points(vix_chart)
    spy_points = extract_daily_points(spy_chart)
    vix_current = vix_points[-1]["close"] if vix_points else None
    vix_previous = vix_points[-2]["close"] if len(vix_points) >= 2 else None
    vix_values = [point["close"] for point in vix_points]
    percentile = (
        round(sum(1 for value in vix_values if value <= vix_current) / len(vix_values) * 100, 1)
        if vix_current is not None and vix_values
        else None
    )
    table = vix_probability_table(vix_points, spy_points)
    current_band = vix_band(vix_current)
    current_row = next((row for row in table if current_band and row["key"] == current_band["key"]), None)

    try:
        fear_greed = get_cnn_fear_greed()
    except Exception:
        proxy_score = round(clamp(100 - (percentile or 50), 0, 100), 1)
        rating, rating_zh = fear_greed_rating_from_score(proxy_score)
        fear_greed = {
            "score": proxy_score,
            "rating": rating,
            "ratingZh": rating_zh,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sourceName": "VIX percentile proxy",
            "sourceUrl": "https://finance.yahoo.com/quote/%5EVIX/",
        }

    payload = {
        "asOf": datetime.now(timezone.utc).isoformat(),
        "source": "数据源：Yahoo Finance ^VIX 与 SPY 日线、CNN Fear & Greed Index；CNN 不可用时使用 VIX 分位代理。",
        "fearGreed": fear_greed,
        "vix": {
            "value": round(vix_current, 2) if vix_current is not None else None,
            "changePct": (
                round(((vix_current / vix_previous) - 1) * 100, 2)
                if vix_current is not None and vix_previous
                else None
            ),
            "date": vix_points[-1]["date"].isoformat() if vix_points else None,
            "percentile10y": percentile,
            "band": current_band["key"] if current_band else None,
            "bandLabel": current_band["label"] if current_band else "--",
            "recommendation": current_row.get("recommendation") if current_row else "--",
            "currentStats": current_row,
            "table": table,
            "sourceName": "Yahoo Finance ^VIX / SPY",
            "sourceUrl": "https://finance.yahoo.com/quote/%5EVIX/",
        },
    }
    return _cache_set("market_sentiment", payload)


def get_btc_tip_height() -> int | None:
    try:
        response = requests.get("https://mempool.space/api/blocks/tip/height", headers=HEADERS, timeout=8)
        response.raise_for_status()
        return int(response.text.strip())
    except (requests.RequestException, TypeError, ValueError):
        return None


def estimate_next_halving(now: datetime) -> dict[str, Any]:
    current_height = get_btc_tip_height()
    if current_height is None:
        estimate_date = ESTIMATED_NEXT_HALVING
        return {
            "date": estimate_date.isoformat(),
            "daysRemaining": max((estimate_date - now.date()).days, 0),
            "currentBlockHeight": None,
            "remainingBlocks": None,
            "targetBlock": NEXT_HALVING_BLOCK,
            "method": "fallback_static_date",
        }

    remaining_blocks = max(NEXT_HALVING_BLOCK - current_height, 0)
    estimate_at = now + timedelta(seconds=remaining_blocks * BITCOIN_AVERAGE_BLOCK_SECONDS)
    return {
        "date": estimate_at.date().isoformat(),
        "daysRemaining": max((estimate_at.date() - now.date()).days, 0),
        "currentBlockHeight": current_height,
        "remainingBlocks": remaining_blocks,
        "targetBlock": NEXT_HALVING_BLOCK,
        "method": "mempool_tip_height_10min_blocks",
    }


def _cycle_day_samples(turns: list[dict[str, Any]], start_key: str, end_key: str) -> list[dict[str, Any]]:
    samples = []
    for turn in turns:
        start_date = turn[start_key]
        end_date = turn[end_key]
        samples.append(
            {
                "cycle": turn["cycle"],
                f"{start_key}Date": start_date.isoformat(),
                f"{end_key}Date": end_date.isoformat(),
                "days": (end_date - start_date).days,
            }
        )
    return samples


def _cycle_day_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    days = [sample["days"] for sample in samples]
    return {
        "averageDays": round(statistics.fmean(days)) if days else None,
        "minDays": min(days) if days else None,
        "maxDays": max(days) if days else None,
        "sampleCount": len(samples),
        "samples": samples,
    }


def _prediction_window(anchor_date: date, summary: dict[str, Any], current_date: date) -> dict[str, Any]:
    if not summary.get("averageDays"):
        return {"anchorDate": anchor_date.isoformat(), "sampleCount": 0}
    average_days = summary["averageDays"]
    min_days = summary["minDays"]
    max_days = summary["maxDays"]
    elapsed_days = max((current_date - anchor_date).days, 0)
    average_date = anchor_date + timedelta(days=average_days)
    earliest_date = anchor_date + timedelta(days=min_days)
    latest_date = anchor_date + timedelta(days=max_days)
    if elapsed_days < min_days:
        window_status = "before_window"
    elif elapsed_days <= max_days:
        window_status = "in_window"
    else:
        window_status = "after_window"
    return {
        "anchorDate": anchor_date.isoformat(),
        "averageDays": average_days,
        "minDays": min_days,
        "maxDays": max_days,
        "averageDate": average_date.isoformat(),
        "earliestDate": earliest_date.isoformat(),
        "latestDate": latest_date.isoformat(),
        "currentDate": current_date.isoformat(),
        "elapsedDays": elapsed_days,
        "daysToAverage": (average_date - current_date).days,
        "progressPct": round(elapsed_days / average_days * 100, 1) if average_days else None,
        "windowStatus": window_status,
        "sampleCount": summary["sampleCount"],
    }


def _cycle_predictions(
    last_halving: date,
    current_bottom: date,
    current_high: dict[str, Any] | None,
    top_to_bottom: dict[str, Any],
    bottom_to_top: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    halving_to_top = _cycle_day_summary(
        _cycle_day_samples(BTC_HALVING_CYCLE_TURNS, "halving", "top")
    )
    halving_to_bottom = _cycle_day_summary(
        _cycle_day_samples(BTC_HALVING_CYCLE_TURNS, "halving", "bottom")
    )
    from_top: dict[str, Any] = {"anchorDate": None, "bottom": None}
    if current_high:
        high_date = current_high["date"]
        from_top = {
            "anchorDate": high_date.isoformat(),
            "anchorPrice": round(current_high["close"], 2),
            "bottom": _prediction_window(high_date, top_to_bottom, today),
        }

    return {
        "method": "使用 2012/2016/2020 三轮减半后的牛熊节奏样本计算均值与历史范围；当前顶部锚点使用本轮最高日收盘价，未确认最终顶部。",
        "fromHalving": {
            "anchorDate": last_halving.isoformat(),
            "top": _prediction_window(last_halving, halving_to_top, today),
            "bottom": _prediction_window(last_halving, halving_to_bottom, today),
        },
        "fromBottom": {
            "anchorDate": current_bottom.isoformat(),
            "top": _prediction_window(current_bottom, bottom_to_top, today),
        },
        "fromTop": from_top,
        "samples": {
            "halvingToTop": halving_to_top,
            "halvingToBottom": halving_to_bottom,
        },
    }


def btc_cycle_rhythm(points: list[dict[str, Any]], today: date) -> dict[str, Any]:
    top_to_bottom = _cycle_day_summary(
        _cycle_day_samples(BTC_TOP_TO_BOTTOM_TURNS, "top", "bottom")
    )
    bottom_to_top = _cycle_day_summary(
        _cycle_day_samples(BTC_BOTTOM_TO_TOP_TURNS, "bottom", "top")
    )

    current_points = [point for point in points if point["date"] >= BTC_CURRENT_CYCLE_BOTTOM]
    current_high = max(current_points, key=lambda point: point["close"]) if current_points else None
    current = {
        "cycleBottomDate": BTC_CURRENT_CYCLE_BOTTOM.isoformat(),
        "method": "当前周期高点使用 Yahoo Finance BTC-USD 日线自 2022-11-21 以来最高收盘价，未确认最终顶部。",
    }

    if current_high:
        high_date = current_high["date"]
        average_cooldown = top_to_bottom["averageDays"]
        current.update(
            {
                "currentHighDate": high_date.isoformat(),
                "currentHighPrice": round(current_high["close"], 2),
                "daysFromBottomToCurrentHigh": (high_date - BTC_CURRENT_CYCLE_BOTTOM).days,
                "daysSinceCurrentHigh": max((today - high_date).days, 0),
                "progressVsAverageBottomToTopPct": (
                    round((high_date - BTC_CURRENT_CYCLE_BOTTOM).days / bottom_to_top["averageDays"] * 100, 1)
                    if bottom_to_top["averageDays"]
                    else None
                ),
            }
        )
        if average_cooldown:
            current["estimatedCoolingLowWindow"] = [
                (high_date + timedelta(days=top_to_bottom["minDays"])).isoformat(),
                (high_date + timedelta(days=top_to_bottom["maxDays"])).isoformat(),
            ]
            current["estimatedCoolingLowAverageDate"] = (
                high_date + timedelta(days=average_cooldown)
            ).isoformat()

    return {
        "topToBottom": top_to_bottom,
        "bottomToTop": bottom_to_top,
        "current": current,
        "predictions": _cycle_predictions(
            HALVINGS[-1],
            BTC_CURRENT_CYCLE_BOTTOM,
            current_high,
            top_to_bottom,
            bottom_to_top,
            today,
        ),
    }


def btc_signal() -> dict[str, Any]:
    cached = _cache_get("btc")
    if cached:
        return cached

    spot = get_btc_spot()
    try:
        chart = yahoo_chart("BTC-USD", "10y", "1d")
    except Exception:
        chart = yahoo_chart("BTC-USD", "5y", "1d")
    daily_points = extract_daily_points(chart)
    closes = [point["close"] for point in daily_points] or extract_closes(chart)
    price = spot["price"] or clean_float(chart.get("meta", {}).get("regularMarketPrice")) or closes[-1]
    rsi14 = rsi(closes)

    now = datetime.now(timezone.utc)
    today = now.date()
    last_halving = HALVINGS[-1]
    days_since = (today - last_halving).days
    next_halving = estimate_next_halving(now)

    try:
        crypto_fear_greed = get_crypto_fear_greed()
    except Exception:
        crypto_fear_greed = {
            "value": None,
            "classification": None,
            "classificationZh": "--",
            "sourceName": "Alternative.me Crypto Fear & Greed Index",
            "sourceUrl": "https://alternative.me/crypto/fear-and-greed-index/",
            "sourceError": "unavailable",
        }

    fear_score = clean_float(crypto_fear_greed.get("value"))
    if fear_score is not None and fear_score <= 25:
        action = "情绪低位观察"
        action_detail = "加密市场恐慌读数偏低，等待价格企稳和成交量确认。"
    elif rsi14 is not None and rsi14 <= 30:
        action = "短线超卖观察"
        action_detail = "RSI 处于偏低区域，关注反弹是否获得持续买盘支持。"
    elif fear_score is not None and fear_score >= 75:
        action = "情绪过热观察"
        action_detail = "加密市场贪婪读数偏高，控制追高节奏并关注波动放大。"
    elif rsi14 is not None and rsi14 >= 70:
        action = "动能过热观察"
        action_detail = "RSI 处于偏高区域，关注价格回落和波动扩大的风险。"
    else:
        action = "等待确认"
        action_detail = "价格、情绪和短线动能尚未形成极端信号，继续观察确认。"

    payload = {
        "asOf": now.isoformat(),
        "source": "数据源：CoinGecko BTC 现价 + Yahoo Finance BTC-USD 日线图表 + mempool.space 最新区块高度 + Alternative.me 恐慌贪婪指数。",
        "price": round(price, 2),
        "change24hPct": round(spot["change24hPct"], 2) if spot.get("change24hPct") is not None else None,
        "marketCap": spot.get("marketCap"),
        "volume24h": spot.get("volume24h"),
        "lastUpdatedAt": spot.get("lastUpdatedAt"),
        "lastHalving": last_halving.isoformat(),
        "nextHalvingEstimate": next_halving["date"],
        "nextHalvingTargetBlock": next_halving["targetBlock"],
        "currentBlockHeight": next_halving["currentBlockHeight"],
        "remainingBlocks": next_halving["remainingBlocks"],
        "nextHalvingMethod": next_halving["method"],
        "daysSinceHalving": days_since,
        "daysToNextHalving": next_halving["daysRemaining"],
        "cycleRhythm": btc_cycle_rhythm(daily_points, today),
        "fearGreed": crypto_fear_greed,
        "rsi14": round(rsi14, 1) if rsi14 else None,
        "action": action,
        "actionDetail": action_detail,
    }
    return _cache_set("btc", payload)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/stocks")
def api_stocks():
    raw = request.args.get("symbols", "").strip()
    min_market_cap_billion = clean_float(request.args.get("min_market_cap_billion"), 100)
    min_market_cap_billion = max(0, min_market_cap_billion if min_market_cap_billion is not None else 100)
    min_market_cap = min_market_cap_billion * 100_000_000
    if raw:
        symbols = [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()][:MAX_SCAN_LIMIT]
        return jsonify(stock_screener(symbols, include_technicals=True))

    try:
        universe_payload = fetch_nasdaq_large_caps(min_market_cap)
        universe = universe_payload["rows"]
    except Exception:
        symbols = FALLBACK_SYMBOLS
        return jsonify(
            stock_screener(
                symbols,
                universe_meta={
                    "universe": "fallback",
                    "universeError": "NASDAQ universe fetch failed; using fallback symbols.",
                    "minMarketCap": min_market_cap,
                    "minMarketCapBillion": min_market_cap_billion,
                    "universeCount": len(symbols),
                    "analyzedCount": len(symbols),
                },
                include_technicals=True,
            )
        )

    requested_limit = clean_int(request.args.get("scan_limit"), DEFAULT_SCAN_LIMIT)
    scan_limit = max(1, min(MAX_SCAN_LIMIT, requested_limit, len(universe)))
    selected = universe[:scan_limit]
    seed_by_symbol = {item["symbol"]: item for item in selected}
    symbols = [item["symbol"] for item in selected]
    return jsonify(
        stock_screener(
            symbols,
            seed_by_symbol=seed_by_symbol,
            universe_meta={
                "universe": "nasdaq_large_cap",
                "universeSource": "https://api.nasdaq.com/api/screener/stocks",
                "minMarketCap": min_market_cap,
                "minMarketCapBillion": min_market_cap_billion,
                "universeCount": len(universe),
                "rawUniverseCount": universe_payload.get("rawCount"),
                "excludedChinaRelated": universe_payload.get("excludedChinaRelated"),
                "analyzedCount": len(selected),
                "includeTechnicals": False,
            },
            include_technicals=False,
        )
    )


@app.get("/api/analyst")
def api_analyst():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    return jsonify(analyst_detail(symbol))


@app.get("/api/btc")
def api_btc():
    return jsonify(btc_signal())


@app.get("/api/market-sentiment")
def api_market_sentiment():
    return jsonify(market_sentiment())


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "time": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
