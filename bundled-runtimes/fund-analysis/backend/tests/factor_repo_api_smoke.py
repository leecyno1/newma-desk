import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repositories.factor_repo import FactorRepo


def main() -> int:
    method = getattr(FactorRepo(), "save_exposures", None)
    if not callable(method):
        print("Expected FactorRepo.save_exposures to exist")
        return 1

    signature = inspect.signature(method)
    if "risk_contributions" not in signature.parameters:
        print(f"Expected save_exposures to accept risk_contributions, got: {signature}")
        return 1

    print("OK FactorRepo.save_exposures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
