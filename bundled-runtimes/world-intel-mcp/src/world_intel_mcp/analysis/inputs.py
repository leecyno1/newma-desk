"""Cycle-local analysis inputs. No persistent cache or second HTTP client."""

import asyncio
import logging
import math

logger = logging.getLogger(__name__)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def input_status(name: str, data: dict) -> str:
    # NGA warnings (including old proxy scores) do not assess cable damage.
    if name == "cable_health":
        return "unavailable"
    if not data or data.get("error") or data.get("_stale") or data.get("freshness") == "stale":
        return "unavailable"
    if data.get("status") in {"unavailable", "error", "stale", "reference_only"}:
        return "unavailable"
    fields = {
        "military_surge": "surge_count", "shipping_index": "stress_score",
        "internet_outages": "ongoing_count", "space_weather": "current_kp",
        "cyber_threats": "count", "disease_outbreaks": "high_concern_count",
    }
    if name in fields and not number(data.get(fields[name])):
        return "unavailable"
    collections = {"theater_posture": "theaters", "instability": "countries",
                   "hotspot_escalation": "hotspots", "cable_health": "corridors",
                   "climate_anomalies": "zones"}
    if name in collections and not data.get(collections[name]):
        return "unavailable"
    if name == "cyber_threats":
        available, expected = data.get("feeds_successful", 0), data.get("feeds_attempted", 4)
        return "ok" if available == expected and expected > 0 else "partial" if available > 0 else "unavailable"
    # These legacy models use static floors/proxies or unverified coverage.
    # Their returned numbers are observations, not a complete live assessment.
    if name in {"instability", "hotspot_escalation"}:
        return "partial"
    return "ok" if data.get("status") == "ok" else "partial"


class AnalysisInputs:
    """One bounded task per source per cycle; all consumers reuse its result."""

    def __init__(self, fetcher):
        from ..sources import climate, cyber, health, infrastructure, intelligence, maritime, military, nuclear, seismology, shipping, space_weather
        from .exposure import fetch_population_exposure

        self.factories = {
            "seismic_catalog": lambda: seismology.fetch_catalog(fetcher),
            "military_flights": lambda: military.fetch_military_flights(fetcher),
            "nav_warnings": lambda: maritime.fetch_nav_warnings(fetcher),
            "instability": lambda: intelligence.fetch_instability_index(fetcher),
            "internet_outages": lambda: infrastructure.fetch_internet_outages(fetcher),
            "shipping_index": lambda: shipping.fetch_shipping_index(fetcher),
            "cyber_threats": lambda: cyber.fetch_cyber_threats(fetcher),
            "disease_outbreaks": lambda: health.fetch_disease_outbreaks(fetcher),
            "climate_anomalies": lambda: climate.fetch_climate_anomalies(fetcher),
            "space_weather": lambda: space_weather.fetch_space_weather(fetcher),
        }

        async def surge():
            return await intelligence.fetch_military_surge(fetcher, posture=await self.get("theater_posture"))

        async def theaters():
            return await military.fetch_theater_posture(fetcher, flights=await self.get("military_flights"))

        async def vessels():
            return await intelligence.fetch_vessel_snapshot(fetcher, nav_data=await self.get("nav_warnings"))

        async def cables():
            return await infrastructure.fetch_cable_health(fetcher, nav_data=await self.get("nav_warnings"))

        async def hotspots():
            return await intelligence.fetch_hotspot_escalation(fetcher)

        async def earthquakes():
            return await seismology.fetch_earthquakes(fetcher, catalog=await self.get("seismic_catalog"))

        async def convergence():
            return await intelligence.fetch_signal_convergence(fetcher, catalog=await self.get("seismic_catalog"))

        async def nuclear_sites():
            return await nuclear.fetch_nuclear_monitor(fetcher, catalog=await self.get("seismic_catalog"))

        async def exposure():
            return await fetch_population_exposure(fetcher, inputs=self)

        self.factories.update(theater_posture=theaters, military_surge=surge, vessel_snapshot=vessels, cable_health=cables, hotspot_escalation=hotspots)
        self.factories.update(earthquakes=earthquakes, signal_convergence=convergence, nuclear_monitor=nuclear_sites, population_exposure=exposure)
        self.tasks = {}

    async def _run(self, name):
        try:
            timeout = 45 if name in {"theater_posture", "military_surge", "vessel_snapshot", "earthquakes", "signal_convergence", "nuclear_monitor", "population_exposure"} else 40
            return await asyncio.wait_for(self.factories[name](), timeout=timeout)
        except Exception as exc:
            logger.warning("Analysis input %s failed: %s", name, exc)
            return {"status": "unavailable", "error": f"{name}: {type(exc).__name__}"}

    async def get(self, name):
        if name not in self.tasks:
            self.tasks[name] = asyncio.create_task(self._run(name))
        # One consumer timing out must not cancel another consumer's input.
        return await asyncio.shield(self.tasks[name])

    async def collect(self, names):
        return dict(zip(names, await asyncio.gather(*(self.get(name) for name in names))))

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
