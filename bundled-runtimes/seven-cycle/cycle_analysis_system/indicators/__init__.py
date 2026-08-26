"""
Indicator registry and data fetchers for the extended macro/market universe.

This package provides:
- A structured registry of indicators (ID, name, category, source, parameters)
- Thin wrappers around Tushare Pro, AkShare, OpenBB etc. to pull raw data
- Helpers to standardise frequencies (yearly/monthly) and derive YoY/MoM
"""

