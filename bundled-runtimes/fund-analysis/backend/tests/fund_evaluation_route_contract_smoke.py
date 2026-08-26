import ast
from pathlib import Path


def main() -> int:
    route_path = Path(__file__).resolve().parents[1] / "routes" / "funds.py"
    tree = ast.parse(route_path.read_text(encoding="utf-8"))

    matched = None
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            first_arg = decorator.args[0]
            if isinstance(first_arg, ast.Constant) and first_arg.value == "/{wind_code}/evaluation":
                matched = node
                break

    if matched is None:
        raise AssertionError("Missing GET /api/funds/{wind_code}/evaluation route")

    source = ast.get_source_segment(route_path.read_text(encoding="utf-8"), matched) or ""
    if "FundEvaluationService" not in source or ".evaluate_fund(" not in source:
        raise AssertionError("Fund evaluation route must delegate to the deep evaluation Module")
    if any(term in source for term in ["planned_amount", "risk_profile", "purchase_gate", "watchlist"]):
        raise AssertionError("Fund evaluation route leaked investment-decision inputs")

    print("OK fund evaluation route delegates to the classification-relative evaluation Module")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
