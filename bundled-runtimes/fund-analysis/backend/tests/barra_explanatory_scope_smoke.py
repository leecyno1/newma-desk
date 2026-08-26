import ast
from pathlib import Path


def main() -> int:
    route_path = Path(__file__).resolve().parents[1] / "routes" / "barra.py"
    source_text = route_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text)

    score_route = None
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            first_arg = decorator.args[0]
            if isinstance(first_arg, ast.Constant) and first_arg.value == "/score/{fund_code}":
                score_route = node
                deprecated_flag = next(
                    (
                        keyword.value.value
                        for keyword in decorator.keywords
                        if keyword.arg == "deprecated" and isinstance(keyword.value, ast.Constant)
                    ),
                    False,
                )
                if deprecated_flag is not True:
                    raise AssertionError("Barra score route must be marked deprecated")
                break

    if score_route is None:
        raise AssertionError("Barra score compatibility route is missing")

    score_source = ast.get_source_segment(source_text, score_route) or ""
    for forbidden in ["volatility_score = 70", "barra_score =", "r2_score * 0.30"]:
        if forbidden in score_source:
            raise AssertionError(f"Barra score still fabricates a fund score: {forbidden}")
    for required in ["deprecated", "explanatory_evidence", "included_in_fund_evaluation_score", "overall_score"]:
        if required not in score_source:
            raise AssertionError(f"Barra score deprecation response missing {required}")

    print("OK Barra is explanatory evidence and no longer fabricates a fund score")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
