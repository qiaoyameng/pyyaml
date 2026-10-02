import pytest

import yaml
from yaml.resource import ResourceBudget, ResourceLimitError


def deep_nesting_source(depth):
    return "[" * depth + "0" + "]" * depth


def alias_source(alias_count):
    return "x: &x 0\ny: [%s]" % ", ".join("*x" for _ in range(alias_count))


def test_resource_limit_error_is_exported():
    assert yaml.ResourceLimitError is ResourceLimitError


def test_nested_depth_exact_limit_is_allowed():
    result = yaml.safe_load(
            deep_nesting_source(5),
            document_budget=ResourceBudget(nested_depth=5),
    )

    assert result == [[[[[0]]]]]


def test_nested_depth_is_checked_before_node_construction():
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(
                deep_nesting_source(6),
                document_budget=ResourceBudget(nested_depth=5),
        )

    error = excinfo.value
    assert error.category == "nested_depth"
    assert error.stage == "composing"
    assert error.scope == "document"
    assert error.limit == 5
    assert error.used == 6
    assert error.mark.line == 0
    assert error.mark.column == 5


def test_scalar_length_is_checked_during_scanning():
    budget = ResourceBudget(scalar_length=4)

    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load("abcde", document_budget=budget)

    error = excinfo.value
    assert error.category == "scalar_length"
    assert error.stage == "scanning"
    assert error.scope == "document"
    assert error.limit == 4
    assert error.used == 5
    assert error.mark.line == 0
    assert error.mark.column == 0


def test_folded_block_scalar_counts_final_spaces():
    result = yaml.safe_load(
            "--- >-\n abc\n def\n",
            document_budget=ResourceBudget(scalar_length=7),
    )

    assert result == "abc def"


def test_stripped_block_scalar_trailing_breaks_are_bounded_during_scanning():
    source = "--- |-\n abc" + "\n" * 100

    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(
                source,
                document_budget=ResourceBudget(scalar_length=10),
        )

    assert excinfo.value.category == "scalar_length"
    assert excinfo.value.stage == "scanning"


def test_node_count_exact_limit_is_allowed():
    result = yaml.safe_load(
            "[0, 1]",
            document_budget=ResourceBudget(node_count=3),
    )

    assert result == [0, 1]


def test_unique_nodes_and_alias_references_are_counted_separately():
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(
                alias_source(3),
                document_budget=ResourceBudget(
                        nested_depth=100,
                        scalar_length=100000,
                        node_count=100,
                        alias_references=2,
                ),
        )

    error = excinfo.value
    assert error.category == "alias_references"
    assert error.used == 3
    assert error.limit == 2


def test_alias_limit_is_exact():
    result = yaml.safe_load(
            alias_source(2),
            document_budget=ResourceBudget(
                    nested_depth=100,
                    scalar_length=100,
                    node_count=100,
                    alias_references=2,
            ),
    )

    assert result == {"x": 0, "y": [0, 0]}


def test_document_budget_resets_for_each_document():
    stream = "---\n[0]\n---\n[0]\n"

    result = list(yaml.safe_load_all(
            stream,
            document_budget=ResourceBudget(
                    nested_depth=1,
                    scalar_length=1,
                    node_count=2,
                    alias_references=0,
            ),
            stream_budget=ResourceBudget(node_count=100),
    ))

    assert result == [[0], [0]]


def test_stream_budget_accumulates_across_documents():
    stream = "---\n[0]\n---\n[0]\n"

    with pytest.raises(ResourceLimitError) as excinfo:
        list(yaml.safe_load_all(
                stream,
                document_budget=ResourceBudget(node_count=100),
                stream_budget=ResourceBudget(node_count=3),
        ))

    error = excinfo.value
    assert error.category == "node_count"
    assert error.scope == "stream"
    assert error.limit == 3
    assert error.used == 4


def test_stream_nested_depth_limit_applies_to_each_document():
    stream = "---\n[[0]]\n---\n0\n"

    with pytest.raises(ResourceLimitError) as excinfo:
        list(yaml.safe_load_all(
                stream,
                document_budget=ResourceBudget(nested_depth=100),
                stream_budget=ResourceBudget(nested_depth=1),
        ))

    assert excinfo.value.category == "nested_depth"
    assert excinfo.value.scope == "stream"


def test_budget_error_releases_composition_state():
    source = "x: &x {nested: *x}\n"
    loader = yaml.SafeLoader(source,
            document_budget=ResourceBudget(
                    nested_depth=1,
                    scalar_length=100,
                    node_count=100,
                    alias_references=100,
            ))

    with pytest.raises(ResourceLimitError):
        loader.get_single_data()

    assert loader.anchors == {}
    assert loader.constructed_objects == {}
    assert loader.recursive_objects == {}
    assert loader.state_generators == []
    assert loader.resource_tracker.document.node_count == 0
    assert loader.resource_tracker.stream.node_count == 2


def test_cyclic_alias_does_not_recurse_through_budget_checking():
    source = "x: &x [*x]\n"
    result = yaml.safe_load(
            source,
            document_budget=ResourceBudget(
                    nested_depth=100,
                    scalar_length=100,
                    node_count=100,
                    alias_references=100,
            ),
    )

    assert result["x"][0] is result["x"]


def test_deep_aliases_are_checked_without_budget_recursion():
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(
                alias_source(1000),
                document_budget=ResourceBudget(
                        nested_depth=100,
                        scalar_length=10000,
                        node_count=2000,
                        alias_references=999,
                ),
        )

    assert excinfo.value.category == "alias_references"
