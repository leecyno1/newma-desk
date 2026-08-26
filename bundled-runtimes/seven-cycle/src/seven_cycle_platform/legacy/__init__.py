"""Bridges from governed legacy research panels into platform inputs."""

from seven_cycle_platform.legacy.research_cycle_input import (
    ResearchCycleInputRequest,
    build_research_cycle_pipeline_input,
)
from seven_cycle_platform.legacy.research_surface_release import (
    ResearchSurfaceReleaseResult,
    build_forward_return_history,
    build_surface_requests,
    publish_research_surface_release,
)

__all__ = [
    "ResearchCycleInputRequest",
    "ResearchSurfaceReleaseResult",
    "build_forward_return_history",
    "build_research_cycle_pipeline_input",
    "build_surface_requests",
    "publish_research_surface_release",
]
