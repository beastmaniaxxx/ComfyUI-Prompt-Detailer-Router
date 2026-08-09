"""Unit tests for resource path resolution (3.10-safe joinpath chaining)."""

import json

from prompt_detailer_router.infrastructure.resource_paths import resource_file


def test_resource_file_reads_nested_schema() -> None:
    text = resource_file("schemas", "detailer_plan_v1.schema.json").read_text(
        encoding="utf-8"
    )
    assert json.loads(text)["title"] == "DETAILER_PLAN v1"


def test_resource_file_reads_deeply_nested_preset() -> None:
    text = resource_file("presets", "detailer", "face.json").read_text(encoding="utf-8")
    assert json.loads(text)["scope"] == "face"


def test_resource_file_single_part() -> None:
    # A single-level directory resolves and is traversable.
    node = resource_file("schemas")
    names = {entry.name for entry in node.iterdir()}
    assert "detailer_plan_v1.schema.json" in names
