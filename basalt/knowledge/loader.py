from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import TypeAdapter

T = TypeVar("T")
KNOWLEDGE = Path(__file__).resolve().parent


def read_yaml(name: str) -> dict:
    with (KNOWLEDGE / name).open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a mapping")
    return value


def validated(value, schema: type[T]) -> T:
    return TypeAdapter(schema).validate_python(value)
