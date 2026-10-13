from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any


class ConditionExpressionError(ValueError):
    """Raised when a workflow condition uses unsupported or invalid syntax."""


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Subscript,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
)


def parse_condition(expression: str) -> ast.Expression | None:
    if not expression.strip():
        return None
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise ConditionExpressionError("invalid workflow condition") from error
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ConditionExpressionError(
                f"unsupported workflow condition syntax: {type(node).__name__}"
            )
    return tree


def resolve_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def evaluate_condition(expression: str, context: Mapping[str, Any]) -> bool:
    tree = parse_condition(expression)
    if tree is None:
        return True
    return bool(_evaluate(tree.body, context))


def _evaluate(node: ast.AST, context: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return context.get(node.id)
    if isinstance(node, ast.Attribute):
        value = _evaluate(node.value, context)
        return value.get(node.attr) if isinstance(value, Mapping) else None
    if isinstance(node, ast.Subscript):
        value = _evaluate(node.value, context)
        key = _evaluate(node.slice, context)
        if isinstance(value, Mapping):
            return value.get(key)
        if isinstance(value, (list, tuple)) and isinstance(key, int):
            return value[key] if 0 <= key < len(value) else None
        return None
    if isinstance(node, ast.List):
        return [_evaluate(item, context) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate(item, context) for item in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _evaluate(key, context): _evaluate(value, context)
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.BoolOp):
        values = (_evaluate(value, context) for value in node.values)
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _evaluate(node.operand, context)
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, context)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate(comparator, context)
            try:
                matched = _compare(operator, left, right)
            except TypeError as error:
                raise ConditionExpressionError(
                    "workflow condition compares incompatible values"
                ) from error
            if not matched:
                return False
            left = right
        return True
    raise ConditionExpressionError(
        f"unsupported workflow condition syntax: {type(node).__name__}"
    )


def _compare(operator: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    raise ConditionExpressionError("unsupported workflow comparison")
