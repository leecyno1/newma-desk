#!/usr/bin/env python3
"""Download and validate the public source files required by C1 research."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output" / "c1_source_refresh.json"
TECHNOLOGY_PATH = PROJECT_ROOT / "data" / "raw" / "worldbank" / "c1_technology_diffusion.csv"
TECHNOLOGY_COUNTRIES = (
    "GBR", "FRA", "NLD", "SWE", "ITA", "DEU", "USA", "CHN",
    "IND", "JPN", "ESP", "CAN", "AUS", "BRA", "KOR",
)
TECHNOLOGY_INDICATORS = {
    "IT.NET.USER.ZS": "internet_users_per_100",
    "IT.CEL.SETS.P2": "mobile_subscriptions_per_100",
    "IT.NET.BBND.P2": "fixed_broadband_per_100",
}


def _read_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "Circle-C1-Research/0.1"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=180) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in {400, 429, 500, 502, 503, 504} or attempt == 4:
                raise
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"无法读取 {url}")


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    path: Path
    minimum_bytes: int


SOURCES = (
    Source(
        "BCL 长期生产率数据库 v2.7",
        "https://www.longtermproductivity.com/download/BCLDatabase_online_v2.7.xlsx",
        PROJECT_ROOT / "data" / "raw" / "bcl" / "BCLDatabase_online_v2.7.xlsx",
        100_000,
    ),
    Source(
        "Comin-Hobijn CHAT 技术扩散数据库",
        "https://data.nber.org/data-appendix/w15319/FinalCHAT_72909.csv",
        PROJECT_ROOT / "data" / "raw" / "chat" / "FinalCHAT_72909.csv",
        1_000_000,
    ),
    Source(
        "JST Macrohistory R6",
        "https://www.macrohistory.net/app/download/9834512469/JSTdatasetR6.xlsx",
        PROJECT_ROOT / "data" / "raw" / "jst" / "JSTdatasetR6.xlsx",
        500_000,
    ),
    Source(
        "全球一次能源结构",
        "https://ourworldindata.org/grapher/global-primary-energy-by-source.csv",
        PROJECT_ROOT / "data" / "raw" / "owid" / "global-primary-energy-by-source.csv",
        300_000,
    ),
    Source(
        "全球一次能源结构元数据",
        "https://ourworldindata.org/grapher/global-primary-energy-by-source.metadata.json",
        PROJECT_ROOT / "data" / "raw" / "owid" / "global-primary-energy-by-source.metadata.json",
        5_000,
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(source: Source, *, refresh: bool) -> str:
    if source.path.exists() and not refresh:
        return "reused"
    source.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = source.path.with_suffix(source.path.suffix + ".part")
    request = Request(source.url, headers={"User-Agent": "Circle-C1-Research/0.1"})
    with urlopen(request, timeout=180) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    temporary.replace(source.path)
    return "downloaded"


def _validate(source: Source) -> dict[str, object]:
    if not source.path.exists():
        raise FileNotFoundError(source.path)
    size = source.path.stat().st_size
    if size < source.minimum_bytes:
        raise ValueError(f"{source.name} 文件过小：{size} bytes")

    if source.path.name.startswith("BCLDatabase"):
        sheets = set(pd.ExcelFile(source.path).sheet_names)
        required = {"Labor Productivity", "TFP"}
        if not required.issubset(sheets):
            raise ValueError(f"BCL 缺少工作表：{sorted(required - sheets)}")
    elif source.path.name.startswith("JSTdataset"):
        try:
            columns = set(pd.read_excel(source.path, nrows=5).columns)
            file_format = "xlsx"
        except ValueError:
            columns = set(pd.read_stata(source.path).columns)
            file_format = "dta"
        required = {"year", "iso", "iy", "imports", "exports", "gdp"}
        if not required.issubset(columns):
            raise ValueError(f"JST 缺少字段：{sorted(required - columns)}")
    elif source.path.name.startswith("FinalCHAT"):
        columns = set(pd.read_csv(source.path, nrows=5).columns)
        required = {"country_name", "year", "computer", "telephone", "elecprod"}
        if not required.issubset(columns):
            raise ValueError(f"CHAT 缺少字段：{sorted(required - columns)}")
    elif source.path.suffix == ".csv":
        frame = pd.read_csv(source.path)
        required = {"Entity", "Year", "Coal", "Oil", "Gas", "Traditional biomass"}
        if not required.issubset(frame.columns) or "World" not in set(frame["Entity"]):
            raise ValueError("全球能源数据缺少 World 序列或核心能源字段")
    else:
        metadata = json.loads(source.path.read_text(encoding="utf-8"))
        if "1800" not in json.dumps(metadata.get("columns", {}), ensure_ascii=False):
            raise ValueError("全球能源元数据未声明 1800 年历史覆盖")

    result = {
        "name": source.name,
        "url": source.url,
        "path": str(source.path.relative_to(PROJECT_ROOT)),
        "bytes": size,
        "sha256": _sha256(source.path),
    }
    if source.path.name.startswith("JSTdataset"):
        result["fileFormat"] = file_format
    return result


def _refresh_technology(*, refresh: bool) -> dict[str, object]:
    if TECHNOLOGY_PATH.exists() and not refresh:
        action = "reused"
    else:
        rows = []
        for indicator, field in TECHNOLOGY_INDICATORS.items():
            for country in TECHNOLOGY_COUNTRIES:
                url = (
                    f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
                    "?format=json&per_page=1000&date=1980%3A2025"
                )
                payload = _read_json(url)
                for item in payload[1] or []:
                    value = item.get("value")
                    if value is None:
                        continue
                    rows.append(
                        {
                            "country": country,
                            "year": int(item["date"]),
                            "indicator": indicator,
                            "field": field,
                            "value": float(value),
                        }
                    )
        frame = pd.DataFrame(rows).sort_values(["country", "year", "indicator"])
        TECHNOLOGY_PATH.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(TECHNOLOGY_PATH, index=False)
        action = "downloaded"

    frame = pd.read_csv(TECHNOLOGY_PATH)
    required = {"country", "year", "indicator", "field", "value"}
    if not required.issubset(frame.columns):
        raise ValueError(f"技术扩散文件缺少字段：{sorted(required - set(frame.columns))}")
    latest = int(frame["year"].max())
    if latest < 2023 or frame["country"].nunique() < 10:
        raise ValueError("世界银行技术扩散数据覆盖不足")
    return {
        "name": "世界银行现代技术扩散桥接",
        "url": "https://api.worldbank.org/v2/",
        "path": str(TECHNOLOGY_PATH.relative_to(PROJECT_ROOT)),
        "bytes": TECHNOLOGY_PATH.stat().st_size,
        "sha256": _sha256(TECHNOLOGY_PATH),
        "action": action,
        "indicators": TECHNOLOGY_INDICATORS,
        "latestYear": latest,
        "latestCountryCount": int(frame.loc[frame["year"].eq(latest), "country"].nunique()),
    }


def refresh_sources(*, refresh: bool = False) -> dict[str, object]:
    rows = []
    for source in SOURCES:
        action = _download(source, refresh=refresh)
        rows.append({**_validate(source), "action": action})
    rows.append(_refresh_technology(refresh=refresh))
    return {
        "asOf": datetime.now(UTC).isoformat(),
        "status": "ready",
        "sources": rows,
        "next": "运行 scripts/research_c1_long_wave_validation.py 重新生成 C1 研究结果。",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    payload = refresh_sources(refresh=args.refresh)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
