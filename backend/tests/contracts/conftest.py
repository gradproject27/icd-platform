import json
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"


def example_text(name: str) -> str:
    return (EXAMPLES_DIR / f"{name}.example.json").read_text(encoding="utf-8")


@pytest.fixture
def load_example():
    """Return the parsed example for a contract name, for example "event"."""
    return lambda name: json.loads(example_text(name))
