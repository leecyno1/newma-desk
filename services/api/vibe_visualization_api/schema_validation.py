from typing import Any, Literal

from jsonschema import Draft202012Validator, SchemaError, ValidationError


SchemaContract = str | dict[str, Any] | None


class JsonContractError(Exception):
    def __init__(self, direction: Literal["input", "output"], message: str):
        super().__init__(message)
        self.direction = direction


def validate_schema_document(schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError("invalid JSON Schema document") from error
    _reject_remote_references(schema)


def _reject_remote_references(value: object) -> None:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str) and not reference.startswith("#"):
            raise ValueError("remote JSON Schema references are not supported")
        for item in value.values():
            _reject_remote_references(item)
    elif isinstance(value, list):
        for item in value:
            _reject_remote_references(item)


def validate_json_contract(
    contract: SchemaContract,
    value: object,
    *,
    direction: Literal["input", "output"],
) -> None:
    # String references remain valid for packaged/legacy Mods. They cannot be
    # certified as runtime-validated until their package resolver is present.
    if contract is None or isinstance(contract, str):
        return
    validate_schema_document(contract)
    try:
        Draft202012Validator(contract).validate(value)
    except ValidationError as error:
        path = ".".join(str(item) for item in error.absolute_path)
        location = f" at {path}" if path else ""
        raise JsonContractError(
            direction,
            f"JSON Schema {direction} validation failed{location}: {error.message}",
        ) from error
