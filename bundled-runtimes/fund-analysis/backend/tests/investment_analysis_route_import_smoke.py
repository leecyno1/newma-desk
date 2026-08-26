import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def main() -> int:
    from routes import investment_analysis

    paths = {route.path for route in investment_analysis.router.routes}
    expected = {
        "/api/investment-analysis/fund/{wind_code}/factor-lens",
        "/api/investment-analysis/fund/{wind_code}/attribution",
    }
    missing = expected - paths
    if missing:
        raise AssertionError(f"Missing investment analysis routes: {missing}")

    print("OK investment analysis route imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
