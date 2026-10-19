from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_docs_are_current() -> None:
    spec = importlib.util.spec_from_file_location(
        "generate_docs", ROOT / "scripts" / "generate_docs.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(check=True) == 0, "run: python scripts/generate_docs.py"


def test_every_field_is_documented() -> None:
    from form4clean.models.transaction import InsiderTransaction

    for name, field in InsiderTransaction.model_fields.items():
        assert field.description, f"{name} has no description"
