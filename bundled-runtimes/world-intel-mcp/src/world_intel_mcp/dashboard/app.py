"""World Intelligence Dashboard — live real-time intelligence overview.

Starlette app serving a self-contained HTML dashboard with SSE streaming.
All data pulled from the same source modules used by the MCP server.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from time import monotonic

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from world_intel_mcp.cache import Cache
from world_intel_mcp.circuit_breaker import CircuitBreaker
from world_intel_mcp.fetcher import Fetcher
from world_intel_mcp.sources import (
    markets,
    seismology,
    military,
    infrastructure,
    maritime,
    economic,
    wildfire,
    cyber,
    news,
    prediction,
    displacement,
    aviation,
    climate,
    conflict,
    intelligence,
    space_weather,
    ai_watch,
    health,
    elections,
    shipping,
    social,
    nuclear,
    service_status,
    traffic,
    webcams,
)
from world_intel_mcp.analysis.alerts import fetch_alert_digest, fetch_weekly_trends
from world_intel_mcp.analysis.posture import fetch_strategic_posture
from world_intel_mcp.analysis.exposure import fetch_population_exposure
from world_intel_mcp.analysis.media_monitor import analyze_media_monitor
from world_intel_mcp.analysis.situation import fetch_situation_brief
from world_intel_mcp.sources.fleet import fetch_fleet_report
from world_intel_mcp.sources.usni_fleet import fetch_usni_fleet
from world_intel_mcp.config.countries import (
    INTEL_HOTSPOTS,
    STRATEGIC_WATERWAYS,
    TIER1_COUNTRIES,
)
from world_intel_mcp.config.geospatial import (
    MILITARY_BASES,
    STRATEGIC_PORTS,
    PIPELINES,
    NUCLEAR_FACILITIES,
)
from world_intel_mcp.sources.infrastructure import CABLE_CORRIDORS
from world_intel_mcp.config.trade_routes import (
    TRADE_ROUTES,
    CLOUD_REGIONS,
    FINANCIAL_CENTERS,
)
from world_intel_mcp.sources.central_banks import fetch_central_bank_rates

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared infrastructure — lazily initialised
# ---------------------------------------------------------------------------
_fetcher: Fetcher | None = None
_cache: Cache | None = None
_breaker: CircuitBreaker | None = None
_vector_store = None
_stream_cycle_lock = asyncio.Lock()
_stream_snapshot: dict = {}
_stream_meta: dict = {}
_stream_completed_at = 0.0
_stream_done = 0
_stream_total = 48
_stream_refresh_seconds = max(
    60,
    int(os.environ.get("WORLD_INTEL_STREAM_REFRESH_SECONDS", "300")),
)


def _stream_cache_is_fresh() -> bool:
    return (
        bool(_stream_snapshot)
        and _stream_completed_at > 0
        and monotonic() - _stream_completed_at < _stream_refresh_seconds
    )


def _stream_replay_payload(*, stale: bool) -> dict | None:
    if not _stream_snapshot:
        return None
    completed = bool(_stream_completed_at and _stream_meta)
    return {
        **_stream_snapshot,
        **_stream_meta,
        "_progressive": False,
        "_complete": completed,
        "_cached": True,
        "_stale": stale,
        "_done": _stream_total if completed else min(_stream_done, _stream_total),
        "_total": _stream_total,
    }


async def _cancel_tasks(tasks: list[asyncio.Task]) -> None:
    pending = [task for task in tasks if not task.done()]
    for task in pending:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def _ensure_fetcher() -> Fetcher:
    global _fetcher, _cache, _breaker, _vector_store
    if _fetcher is None:
        _cache = Cache()
        _breaker = CircuitBreaker()
        # Vector store is optional. Do not start its worker when dependencies
        # are absent, otherwise every successful fetch produces a warning.
        try:
            from world_intel_mcp.vector_store import VectorStore

            vector_ready = find_spec("qdrant_client") is not None and find_spec("fastembed") is not None
            _vector_store = VectorStore(enabled=True) if vector_ready else None
        except Exception:
            logger.info("Vector store unavailable in dashboard mode")
        _fetcher = Fetcher(cache=_cache, breaker=_breaker, vector_store=_vector_store)
    return _fetcher


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


async def _fetch_overview() -> dict:
    """Fetch all dashboard domains in parallel, return unified dict."""
    fetcher = _ensure_fetcher()

    coros = {
        "market_quotes": markets.fetch_market_quotes(fetcher),
        "crypto_quotes": markets.fetch_crypto_quotes(fetcher),
        "macro_signals": markets.fetch_macro_signals(fetcher),
        "sector_heatmap": markets.fetch_sector_heatmap(fetcher),
        "earthquakes": seismology.fetch_earthquakes(fetcher),
        "military_flights": military.fetch_military_flights(fetcher),
        "cyber_threats": cyber.fetch_cyber_threats(fetcher),
        "news_bundle": news.fetch_news_bundle(fetcher),
        "nav_warnings": maritime.fetch_nav_warnings(fetcher),
        "internet_outages": infrastructure.fetch_internet_outages(fetcher),
        "cable_health": infrastructure.fetch_cable_health(fetcher),
        "wildfires": wildfire.fetch_wildfires(fetcher),
        "prediction_markets": prediction.fetch_prediction_markets(fetcher),
        "airport_delays": aviation.fetch_airport_delays(fetcher),
        "climate_anomalies": climate.fetch_climate_anomalies(fetcher),
        "energy_prices": economic.fetch_energy_prices(fetcher),
        "gas_prices": economic.fetch_gas_prices(fetcher),
        "residential_natgas": economic.fetch_residential_natgas_prices(fetcher),
        "electricity_rates": economic.fetch_electricity_rates(fetcher),
        "stablecoin_status": markets.fetch_stablecoin_status(fetcher),
        "etf_flows": markets.fetch_etf_flows(fetcher),
        "acled_events": conflict.fetch_acled_events(fetcher),
        "ucdp_events": conflict.fetch_ucdp_events(fetcher),
        "displacement": displacement.fetch_displacement_summary(fetcher),
        "risk_scores": intelligence.fetch_risk_scores(fetcher),
        "signal_convergence": intelligence.fetch_signal_convergence(fetcher),
        "space_weather": space_weather.fetch_space_weather(fetcher),
        "ai_watch": ai_watch.fetch_ai_watch(fetcher),
        "disease_outbreaks": health.fetch_disease_outbreaks(fetcher),
        "election_calendar": elections.fetch_election_calendar(fetcher),
        "shipping_index": shipping.fetch_shipping_index(fetcher),
        "social_signals": social.fetch_social_signals(fetcher),
        "nuclear_monitor": nuclear.fetch_nuclear_monitor(fetcher),
        "alert_digest": fetch_alert_digest(fetcher),
        "weekly_trends": fetch_weekly_trends(fetcher),
        "service_status": service_status.fetch_service_status(fetcher),
        "strategic_posture": fetch_strategic_posture(fetcher),
        "fleet_report": fetch_fleet_report(fetcher),
        "usni_fleet": fetch_usni_fleet(fetcher),
        "population_exposure": fetch_population_exposure(fetcher),
        "domestic_flights": aviation.fetch_domestic_flights(fetcher),
        "traffic_flow": traffic.fetch_traffic_flow(fetcher),
        "traffic_incidents": traffic.fetch_traffic_incidents(fetcher),
        "webcams": webcams.fetch_webcams(fetcher),
        "btc_technicals": markets.fetch_btc_technicals(fetcher),
        "central_bank_rates": fetch_central_bank_rates(fetcher),
    }

    # Per-coro timeout so no single slow source blocks the entire dashboard.
    # The shared news bundle gets extra time for the RSS fan-out.
    _SLOW_SOURCES = {
        "news_bundle",
        "alert_digest",
        "weekly_trends",
        "strategic_posture",
    }

    async def _with_timeout(name: str, coro, timeout: float = 45.0):
        effective = 90.0 if name in _SLOW_SOURCES else timeout
        try:
            return await asyncio.wait_for(coro, timeout=effective)
        except asyncio.TimeoutError:
            logger.warning("Dashboard fetch %s timed out after %.0fs", name, effective)
            return {"error": f"timeout after {effective}s", "_timeout": True}

    gathered = await asyncio.gather(
        *[_with_timeout(name, c) for name, c in zip(coros.keys(), coros.values())],
        return_exceptions=True,
    )

    result: dict = {}
    for name, data in zip(coros.keys(), gathered):
        if isinstance(data, Exception):
            logger.warning("Dashboard fetch %s failed: %s", name, data)
            error = {"error": type(data).__name__ + ": " + str(data)[:120]}
            if name == "news_bundle":
                result.update({"news_feed": error, "trending_keywords": error})
            else:
                result[name] = error
        elif name == "news_bundle":
            if "news_feed" in data:
                result.update(data)
            else:
                result.update({"news_feed": data, "trending_keywords": data})
        else:
            result[name] = data

    # The news bundle already analyses the broader 200-item batch. Reuse that
    # result unless social signals are available and need to be merged.
    bundled_monitor = result.get("media_monitor")
    social_posts = result.get("social_signals", {}).get("posts", [])
    if social_posts:
        result["media_monitor"] = analyze_media_monitor(
            result.get("news_feed", {}).get("items", []),
            social_posts,
        )
    elif not isinstance(bundled_monitor, dict):
        result["media_monitor"] = analyze_media_monitor(
            result.get("news_feed", {}).get("items", []),
        )

    # Conflict zone fallback: when both ACLED and UCDP fail, provide
    # static hotspot data so the conflict layer is never empty.
    acled = result.get("acled_events", {})
    ucdp = result.get("ucdp_events", {})
    acled_ok = not acled.get("error") and (acled.get("count") or 0) > 0
    ucdp_ok = not ucdp.get("error") and (ucdp.get("count") or 0) > 0
    if not acled_ok and not ucdp_ok:
        escalation_labels = {
            1: "low",
            2: "low",
            3: "moderate",
            4: "high",
            5: "critical",
        }
        # Map ISO codes to country names for richer display
        _iso_names = {c: info["name"] for c, info in TIER1_COUNTRIES.items()}
        hotspot_events = []
        for name, h in INTEL_HOTSPOTS.items():
            assoc = h.get("associated_countries", [])
            country_name = _iso_names.get(assoc[0], "") if assoc else ""
            actors = [_iso_names.get(c, c) for c in assoc]
            esc = h["baseline_escalation"]
            hotspot_events.append(
                {
                    "latitude": h["lat"],
                    "longitude": h["lon"],
                    "country": country_name or name.replace("_", " ").title(),
                    "location": name.replace("_", " ").title(),
                    "event_type": "Active Hotspot",
                    "type_of_violence_label": "active hotspot",
                    "fatalities": 0,
                    "best": 0,
                    "escalation": esc,
                    "severity": escalation_labels.get(esc, "unknown"),
                    "event_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "actor1": actors[0] if len(actors) > 0 else "\u2014",
                    "actor2": actors[1] if len(actors) > 1 else "\u2014",
                    "source": "Intel Hotspot Database",
                    "notes": f"Escalation level {esc}/5 ({escalation_labels.get(esc, 'unknown')}). "
                    f"Monitored hotspot involving {', '.join(actors)}.",
                    "associated_countries": assoc,
                }
            )
        result["conflict_zones"] = {
            "events": hotspot_events,
            "count": len(hotspot_events),
            "source": "intel-hotspots",
        }

    # Static geospatial datasets (no API calls)
    result["military_bases"] = {"bases": MILITARY_BASES, "count": len(MILITARY_BASES)}
    result["strategic_ports"] = {
        "ports": STRATEGIC_PORTS,
        "count": len(STRATEGIC_PORTS),
    }
    result["pipelines"] = {"pipelines": PIPELINES, "count": len(PIPELINES)}
    result["nuclear_facilities"] = {
        "facilities": NUCLEAR_FACILITIES,
        "count": len(NUCLEAR_FACILITIES),
    }
    result["waterways"] = {
        "waterways": STRATEGIC_WATERWAYS,
        "count": len(STRATEGIC_WATERWAYS),
    }
    result["trade_routes"] = {"routes": TRADE_ROUTES, "count": len(TRADE_ROUTES)}
    result["cloud_regions"] = {"regions": CLOUD_REGIONS, "count": len(CLOUD_REGIONS)}
    result["financial_centers"] = {
        "centers": FINANCIAL_CENTERS,
        "count": len(FINANCIAL_CENTERS),
    }
    result["cable_corridors"] = {
        "corridors": [
            {
                "name": n,
                "lat_range": c["lat_range"],
                "lon_range": c["lon_range"],
                "cables": c["cables"],
            }
            for n, c in CABLE_CORRIDORS.items()
        ],
        "count": len(CABLE_CORRIDORS),
    }

    # AI situational brief (runs after main gather so it has all data)
    try:
        result["situation_brief"] = await asyncio.wait_for(
            fetch_situation_brief(result),
            timeout=35.0,
        )
    except Exception as exc:
        logger.warning("Situation brief failed: %s", exc)
        result["situation_brief"] = {"error": str(exc)}

    # Attach source health + timestamp
    result["source_health"] = _breaker.status() if _breaker else {}
    result["cache_stats"] = _cache.stats() if _cache else {}
    result["cache_freshness"] = _cache.freshness() if _cache else {}
    result["timestamp"] = datetime.now(timezone.utc).isoformat()

    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def index(request):
    """Serve the dashboard HTML page (reloads on each request during dev)."""
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())


async def api_overview(request):
    """REST endpoint — full snapshot of all intelligence domains."""
    data = await _fetch_overview()
    return JSONResponse(data, headers={"Access-Control-Allow-Origin": "*"})


async def api_stream(request):
    """SSE endpoint — shared progressive collection with cached replay."""

    async def event_generator():
        global _stream_completed_at, _stream_done, _stream_meta, _stream_snapshot, _stream_total

        tasks: list[asyncio.Task] = []

        try:
            while True:
                cache_is_fresh = _stream_cache_is_fresh()
                replay = _stream_replay_payload(stale=not cache_is_fresh)
                if replay:
                    yield f"data: {json.dumps(replay, default=str)}\n\n"
                if cache_is_fresh:
                    while _stream_cache_is_fresh():
                        await asyncio.sleep(min(15, _stream_refresh_seconds))
                        yield ": keepalive\n\n"
                    continue

                while _stream_cycle_lock.locked():
                    yield ": keepalive\n\n"
                    await asyncio.sleep(2)

                async with _stream_cycle_lock:
                    if _stream_cache_is_fresh():
                        continue

                    fetcher = _ensure_fetcher()

                    # Sources to fetch, grouped so fast ones arrive first
                    source_defs = {
                        "market_quotes": lambda: markets.fetch_market_quotes(fetcher),
                        "crypto_quotes": lambda: markets.fetch_crypto_quotes(fetcher),
                        "macro_signals": lambda: markets.fetch_macro_signals(fetcher),
                        "sector_heatmap": lambda: markets.fetch_sector_heatmap(fetcher),
                        "earthquakes": lambda: seismology.fetch_earthquakes(fetcher),
                        "military_flights": lambda: military.fetch_military_flights(fetcher),
                        "cyber_threats": lambda: cyber.fetch_cyber_threats(fetcher),
                        "news_bundle": lambda: news.fetch_news_bundle(fetcher),
                        "nav_warnings": lambda: maritime.fetch_nav_warnings(fetcher),
                        "internet_outages": lambda: infrastructure.fetch_internet_outages(fetcher),
                        "cable_health": lambda: infrastructure.fetch_cable_health(fetcher),
                        "wildfires": lambda: wildfire.fetch_wildfires(fetcher),
                        "prediction_markets": lambda: prediction.fetch_prediction_markets(fetcher),
                        "airport_delays": lambda: aviation.fetch_airport_delays(fetcher),
                        "climate_anomalies": lambda: climate.fetch_climate_anomalies(fetcher),
                        "energy_prices": lambda: economic.fetch_energy_prices(fetcher),
                        "gas_prices": lambda: economic.fetch_gas_prices(fetcher),
                        "residential_natgas": lambda: economic.fetch_residential_natgas_prices(fetcher),
                        "electricity_rates": lambda: economic.fetch_electricity_rates(fetcher),
                        "stablecoin_status": lambda: markets.fetch_stablecoin_status(fetcher),
                        "etf_flows": lambda: markets.fetch_etf_flows(fetcher),
                        "acled_events": lambda: conflict.fetch_acled_events(fetcher),
                        "ucdp_events": lambda: conflict.fetch_ucdp_events(fetcher),
                        "displacement": lambda: displacement.fetch_displacement_summary(fetcher),
                        "risk_scores": lambda: intelligence.fetch_risk_scores(fetcher),
                        "signal_convergence": lambda: intelligence.fetch_signal_convergence(fetcher),
                        "space_weather": lambda: space_weather.fetch_space_weather(fetcher),
                        "ai_watch": lambda: ai_watch.fetch_ai_watch(fetcher),
                        "disease_outbreaks": lambda: health.fetch_disease_outbreaks(fetcher),
                        "election_calendar": lambda: elections.fetch_election_calendar(fetcher),
                        "shipping_index": lambda: shipping.fetch_shipping_index(fetcher),
                        "social_signals": lambda: social.fetch_social_signals(fetcher),
                        "nuclear_monitor": lambda: nuclear.fetch_nuclear_monitor(fetcher),
                        "alert_digest": lambda: fetch_alert_digest(fetcher),
                        "weekly_trends": lambda: fetch_weekly_trends(fetcher),
                        "service_status": lambda: service_status.fetch_service_status(fetcher),
                        "strategic_posture": lambda: fetch_strategic_posture(fetcher),
                        "fleet_report": lambda: fetch_fleet_report(fetcher),
                        "usni_fleet": lambda: fetch_usni_fleet(fetcher),
                        "population_exposure": lambda: fetch_population_exposure(fetcher),
                        "domestic_flights": lambda: aviation.fetch_domestic_flights(fetcher),
                        "traffic_flow": lambda: traffic.fetch_traffic_flow(fetcher),
                        "traffic_incidents": lambda: traffic.fetch_traffic_incidents(fetcher),
                        "webcams": lambda: webcams.fetch_webcams(fetcher),
                        "btc_technicals": lambda: markets.fetch_btc_technicals(fetcher),
                        "central_bank_rates": lambda: fetch_central_bank_rates(fetcher),
                    }

                    _SLOW = {
                        "news_bundle", "alert_digest",
                        "weekly_trends", "strategic_posture",
                    }
                    results_q: asyncio.Queue = asyncio.Queue()

                    async def _run_source(name: str, factory):
                        timeout = 90.0 if name in _SLOW else 45.0
                        try:
                            data = await asyncio.wait_for(factory(), timeout=timeout)
                        except asyncio.TimeoutError:
                            data = {"error": f"timeout after {timeout}s", "_timeout": True}
                        except Exception as exc:
                            data = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                        await results_q.put((name, data))

                    # Fire one shared collection cycle for all subscribers.
                    tasks = [
                        asyncio.create_task(_run_source(name, factory))
                        for name, factory in source_defs.items()
                    ]
                    source_total = len(tasks)
                    total = source_total + 2
                    _stream_total = total
                    _stream_done = 0
                    completed = 0
                    cycle_snapshot: dict = {}

                    # Yield each result as it arrives. If a transient failure
                    # follows a successful cycle, retain the last usable data
                    # and attach the error for the health console.
                    while completed < source_total:
                        try:
                            name, data = await asyncio.wait_for(results_q.get(), timeout=120)
                        except asyncio.TimeoutError:
                            break
                        completed += 1
                        _stream_done = completed
                        domains = data if name == "news_bundle" and "news_feed" in data else {name: data}
                        if name == "news_bundle" and "news_feed" not in data:
                            domains = {"news_feed": data, "trending_keywords": data}
                        published_domains: dict = {}
                        for domain, value in domains.items():
                            previous = _stream_snapshot.get(domain)
                            if isinstance(value, dict) and value.get("error") and isinstance(previous, dict):
                                published = {
                                    **previous,
                                    "error": value["error"],
                                    "_stale": True,
                                    **({"_timeout": True} if value.get("_timeout") else {}),
                                }
                            else:
                                published = value
                            _stream_snapshot[domain] = published
                            published_domains[domain] = published
                        cycle_snapshot.update(published_domains)
                        payload = json.dumps(
                            {
                                "_progressive": True,
                                "_complete": False,
                                "_cached": False,
                                "_stale": False,
                                "_done": completed,
                                "_total": total,
                                **published_domains,
                            },
                            default=str,
                        )
                        yield f"data: {payload}\n\n"

                    bundled_monitor = cycle_snapshot.get("media_monitor")
                    social_posts = cycle_snapshot.get("social_signals", {}).get("posts", [])
                    media_monitor = analyze_media_monitor(
                        cycle_snapshot.get("news_feed", {}).get("items", []),
                        social_posts,
                    ) if social_posts or not isinstance(bundled_monitor, dict) else bundled_monitor
                    completed += 1
                    _stream_done = completed
                    _stream_snapshot["media_monitor"] = media_monitor
                    yield f"data: {json.dumps({'_progressive': True, '_complete': False, '_cached': False, '_stale': False, '_done': completed, '_total': total, 'media_monitor': media_monitor}, default=str)}\n\n"

                    # Generate a fast deterministic brief from the completed cycle.
                    try:
                        situation_brief = await fetch_situation_brief(cycle_snapshot, use_ai=False)
                    except Exception as exc:
                        situation_brief = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                    completed += 1
                    _stream_done = completed
                    _stream_snapshot["situation_brief"] = situation_brief
                    yield f"data: {json.dumps({'_progressive': True, '_complete': False, '_cached': False, '_stale': False, '_done': completed, '_total': total, 'situation_brief': situation_brief}, default=str)}\n\n"

                    # Final event with metadata, cached for instant replay to
                    # later subscribers without another 47-source fan-out.
                    _stream_meta = {
                        "source_health": _breaker.status() if _breaker else {},
                        "cache_stats": _cache.stats() if _cache else {},
                        "cache_freshness": _cache.freshness() if _cache else {},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    _stream_completed_at = monotonic()
                    _stream_done = total
                    meta = {
                        "_progressive": False,
                        "_complete": True,
                        "_cached": False,
                        "_stale": False,
                        "_done": total,
                        "_total": total,
                        **_stream_meta,
                    }
                    yield f"data: {json.dumps(meta, default=str)}\n\n"

                    await _cancel_tasks(tasks)
                    tasks = []

                while _stream_cache_is_fresh():
                    await asyncio.sleep(min(15, _stream_refresh_seconds))
                    yield ": keepalive\n\n"

        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("SSE tick failed")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            # Starlette cancels the generator as soon as a browser tab, iframe,
            # or proxy disconnects. Reap every source task on that path too;
            # otherwise repeated Mod opens leave a growing fan-out behind and
            # can starve the dashboard health endpoint.
            await _cancel_tasks(tasks)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def api_static(request):
    """Return static geospatial datasets instantly (no API calls).

    The dashboard fetches this on boot so the infrastructure layer
    populates immediately without waiting for the full SSE gather.
    """
    return JSONResponse(
        {
            "_progressive": False,
            "_complete": True,
            "_static": True,
            "_done": 1,
            "_total": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "military_bases": {"bases": MILITARY_BASES, "count": len(MILITARY_BASES)},
            "strategic_ports": {
                "ports": STRATEGIC_PORTS,
                "count": len(STRATEGIC_PORTS),
            },
            "pipelines": {"pipelines": PIPELINES, "count": len(PIPELINES)},
            "nuclear_facilities": {
                "facilities": NUCLEAR_FACILITIES,
                "count": len(NUCLEAR_FACILITIES),
            },
            "waterways": {
                "waterways": STRATEGIC_WATERWAYS,
                "count": len(STRATEGIC_WATERWAYS),
            },
            "cable_corridors": {
                "corridors": [
                    {
                        "name": n,
                        "lat_range": c["lat_range"],
                        "lon_range": c["lon_range"],
                        "cables": c["cables"],
                    }
                    for n, c in CABLE_CORRIDORS.items()
                ],
                "count": len(CABLE_CORRIDORS),
            },
            "trade_routes": {"routes": TRADE_ROUTES, "count": len(TRADE_ROUTES)},
            "cloud_regions": {"regions": CLOUD_REGIONS, "count": len(CLOUD_REGIONS)},
            "financial_centers": {
                "centers": FINANCIAL_CENTERS,
                "count": len(FINANCIAL_CENTERS),
            },
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )


async def api_health(request):
    """Health check."""
    return JSONResponse({"status": "ok"})


async def api_report_pdf(request):
    """PDF report generation (removed — use the live dashboard instead)."""
    return JSONResponse(
        {"error": "PDF reports removed — use the live dashboard at /"},
        status_code=410,
    )


async def sse_vector_analytics(request):
    """SSE endpoint — pushes vector store analytics every 30 seconds."""

    async def event_generator():
        while True:
            try:
                payload = await _fetch_vector_analytics()
                yield f"data: {json.dumps(payload, default=str)}\n\n"
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.exception("Vector analytics SSE tick failed")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def _fetch_vector_analytics() -> dict:
    """Gather vector store stats, domain summary, and trend detection."""
    _ensure_fetcher()
    if _vector_store is None:
        return {
            "available": False,
            "error": "Vector store not available (Qdrant not running)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    stats_coro = _vector_store.collection_stats()
    domain_coro = _vector_store.domain_summary(hours=24.0)
    trend_coro = _vector_store.trend_detection(recent_hours=6.0, baseline_hours=48.0)

    gathered = await asyncio.gather(
        stats_coro, domain_coro, trend_coro, return_exceptions=True
    )

    result: dict = {"available": True}
    names = ("stats", "domain_summary", "trends")
    for name, data in zip(names, gathered):
        if isinstance(data, Exception):
            logger.warning("Vector analytics %s failed: %s", name, data)
            result[name] = {"error": str(data)}
        else:
            result[name] = data
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return result


async def api_vector_search(request):
    """POST endpoint for semantic search against the vector store."""
    _ensure_fetcher()
    if _vector_store is None:
        return JSONResponse(
            {"error": "Vector store not available (Qdrant not running)"},
            status_code=503,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Invalid JSON body"},
            status_code=400,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    query = body.get("query", "").strip()
    if not query:
        return JSONResponse(
            {"error": "Missing 'query' parameter"},
            status_code=400,
            headers={"Access-Control-Allow-Origin": "*"},
        )

    hours = body.get("hours")
    category = body.get("category")
    limit = min(int(body.get("limit", 20)), 50)

    try:
        results = await _vector_store.semantic_search(
            query=query,
            limit=limit,
            category=category,
            hours=float(hours) if hours else None,
        )
        return JSONResponse(results, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as exc:
        logger.exception("Vector search failed")
        return JSONResponse(
            {"error": str(exc)},
            status_code=500,
            headers={"Access-Control-Allow-Origin": "*"},
        )


async def api_vector_search_options(request):
    """CORS preflight for vector search."""
    return JSONResponse(
        {},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app):
    """Start/stop vector store worker alongside the app."""
    _ensure_fetcher()
    if _vector_store:
        await _vector_store.start()
        logger.info("Dashboard vector store worker started")
    yield
    if _vector_store:
        await _vector_store.stop()
        logger.info("Dashboard vector store worker stopped")


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/overview", api_overview),
        Route("/api/stream", api_stream),
        Route("/api/static", api_static),
        Route("/api/health", api_health),
        Route("/api/report/pdf", api_report_pdf),
        Route("/sse/vector-analytics", sse_vector_analytics),
        Route("/api/vector-search", api_vector_search, methods=["POST"]),
        Route("/api/vector-search", api_vector_search_options, methods=["OPTIONS"]),
    ],
    lifespan=lifespan,
)


def _parse_run_args(argv: list[str] | None = None) -> tuple[str, int]:
    """Parse dashboard CLI args for the console script and module runner."""
    import argparse
    import os

    default_port = int(
        os.environ.get(
            "WORLD_INTEL_DASHBOARD_PORT",
            os.environ.get("PORT", "8501"),
        )
    )
    parser = argparse.ArgumentParser(description="Run the World Intelligence dashboard")
    parser.add_argument(
        "--host",
        default=os.environ.get("WORLD_INTEL_DASHBOARD_HOST", "127.0.0.1"),
        help="Interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="Port to bind (default: 8501, or WORLD_INTEL_DASHBOARD_PORT/PORT)",
    )
    args = parser.parse_args(argv)
    return args.host, args.port


def run(host: str | None = None, port: int | None = None) -> None:
    """Launch the dashboard server."""
    import uvicorn

    if host is None or port is None:
        parsed_host, parsed_port = _parse_run_args()
        host = host or parsed_host
        port = parsed_port if port is None else port

    logger.info("Starting Intelligence Dashboard on http://%s:%d", host, port)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    run()
