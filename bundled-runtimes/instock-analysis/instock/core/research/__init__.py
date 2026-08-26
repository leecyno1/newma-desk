"""Deterministic research modules hosted by the InStock analysis runtime."""

from .supply_chain import (
    IndustryChainResearchEngine,
    IndustryChainResearchError,
    SupplyChainResearchEngine,
    SupplyChainResearchError,
)
from .stock_dossier import StockResearchDossier, StockResearchError
from .event_flow import EventFlowEngine, EventFlowError
from .research_book import ResearchBookEngine, ResearchBookError

__all__ = [
    "IndustryChainResearchEngine",
    "IndustryChainResearchError",
    "SupplyChainResearchEngine",
    "SupplyChainResearchError",
    "StockResearchDossier",
    "StockResearchError",
    "EventFlowEngine",
    "EventFlowError",
    "ResearchBookEngine",
    "ResearchBookError",
]
