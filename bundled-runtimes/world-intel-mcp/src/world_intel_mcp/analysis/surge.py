"""Reference region boundaries for observed ADS-B samples, not deployments."""

from __future__ import annotations


SENSITIVE_REGIONS: dict[str, dict] = {
    "persian_gulf": {
        "bbox": "20,45,30,60",
    },
    "taiwan_strait": {
        "bbox": "21,116,27,123",
    },
    "baltic_sea": {
        "bbox": "53,10,66,30",
    },
    "south_china_sea": {
        "bbox": "0,100,25,122",
    },
    "korean_dmz": {
        "bbox": "33,124,43,132",
    },
    "black_sea": {
        "bbox": "40,27,47,42",
    },
    "red_sea": {
        "bbox": "12,32,30,44",
    },
    "arctic": {
        "bbox": "65,-180,90,180",
    },
}
