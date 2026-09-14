"""UAT-007: `RunRequest.dataset_reference`'s published OpenAPI schema must be a
real `anyOf` over named shapes, each with at least one example -- not a bare
`additionalProperties: true` blob. This is a schema-typing-only change
(`naive_first_common.contracts.DatasetReferenceType`); the field's actual
runtime/validation type stays plain `dict`, proven separately by
`test_runs_routing.py`/`test_downstream_failures.py` still submitting plain
dicts unchanged.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _dataset_reference_schema() -> dict:
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    return schema["components"]["schemas"]["RunRequest"]["properties"]["dataset_reference"]


def test_dataset_reference_is_not_bare_additional_properties() -> None:
    field_schema = _dataset_reference_schema()

    assert field_schema.get("type") != "object"
    assert "additionalProperties" not in field_schema
    assert "anyOf" in field_schema


def test_dataset_reference_anyof_has_four_named_shapes_each_with_an_example() -> None:
    field_schema = _dataset_reference_schema()
    shapes = field_schema["anyOf"]

    titles = {shape["title"] for shape in shapes}
    assert titles == {
        "PathDatasetReference",
        "InlineDatasetReference",
        "StoredDatasetReference",
        "ObjectKeyDatasetReference",
    }

    for shape in shapes:
        # every shape must carry at least one example, on at least one of its
        # own properties (the field-level example, not a whole-shape example)
        assert any(
            "examples" in prop_schema for prop_schema in shape["properties"].values()
        ), f"{shape['title']} has no example on any property"
