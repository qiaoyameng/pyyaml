import pytest

import yaml


def loader_classes():
    classes = [yaml.SafeLoader]
    if hasattr(yaml, "CSafeLoader"):
        classes.append(yaml.CSafeLoader)
    return classes


def flatten_mapping_keys(source, name, Loader):
    loader = Loader(source)
    try:
        root = loader.get_single_node()
        for key_node, value_node in root.value:
            if key_node.value == name:
                loader.flatten_mapping(value_node)
                return [key_node.value for key_node, value_node in value_node.value]
        raise AssertionError("mapping %r was not found" % name)
    finally:
        loader.dispose()


def merge_fanout_source(levels, width):
    lines = [
        "n0: &n0 {%s}" % ", ".join(
            "k%s: %s" % (index, index) for index in range(width)
        )
    ]
    previous = "n0"
    for level in range(1, levels+1):
        prefix = chr(ord("a") + level - 1)
        aliases = []
        for index in range(width):
            name = "%s%s" % (prefix, index)
            lines.append("%s: &%s {<<: *%s}" % (name, name, previous))
            aliases.append("*%s" % name)
        current = "n%s" % level
        lines.append("%s: &%s {<<: [%s]}" % (current, current, ",".join(aliases)))
        previous = current
    lines.append("root: {<<: *%s}" % previous)
    return "\n".join(lines)


@pytest.mark.parametrize("Loader", loader_classes())
def test_flatten_mapping_skips_duplicate_sequence_merge_nodes(Loader):
    keys = flatten_mapping_keys(
        """
base: &base {x: 1, y: 2}
target:
  <<: [*base, *base]
  z: 3
""",
        "target",
        Loader,
    )

    assert keys == ["x", "y", "z"]


@pytest.mark.parametrize("Loader", loader_classes())
def test_flatten_mapping_skips_duplicate_direct_merge_nodes(Loader):
    keys = flatten_mapping_keys(
        """
base: &base {x: 1, y: 2}
target:
  <<: *base
  <<: *base
  z: 3
""",
        "target",
        Loader,
    )

    assert keys == ["x", "y", "z"]


@pytest.mark.parametrize("Loader", loader_classes())
def test_flatten_mapping_skips_nested_duplicate_merge_nodes(Loader):
    keys = flatten_mapping_keys(
        """
a0: &a0 {k0: 0}
a1: &a1
  <<: [*a0, *a0]
  k1: 1
a2: &a2
  <<: [*a1, *a1]
  k2: 2
target:
  <<: [*a2, *a2]
  k3: 3
""",
        "target",
        Loader,
    )

    assert keys == ["k0", "k1", "k2", "k3"]


@pytest.mark.parametrize("Loader", loader_classes())
def test_flatten_mapping_deduplicates_fanout_merge_keys(Loader):
    keys = flatten_mapping_keys(
        merge_fanout_source(levels=4, width=4),
        "root",
        Loader,
    )

    assert keys == ["k0", "k1", "k2", "k3"]


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_key_policy_rejects_explicit_duplicates(Loader):
    with pytest.raises(yaml.constructor.ConstructorError) as excinfo:
        yaml.load(
            "top:\n"
            "  child:\n"
            "    timeout: 1\n"
            "    timeout: 2\n",
            Loader,
            duplicate_key_policy=yaml.DuplicateKeyPolicy.REJECT,
        )

    error = excinfo.value
    assert error.context_mark.line == 2
    assert error.context_mark.column == 4
    assert error.problem_mark.line == 3
    assert error.problem_mark.column == 4
    assert "duplicate key 'timeout'" in str(error)
    assert "mapping path: <root>.top.child" in str(error)


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_key_policy_first_and_last(Loader):
    source = "timeout: 1\ntimeout: 2\n"

    assert yaml.load(source, Loader, duplicate_key_policy="first") == {
        "timeout": 1,
    }
    assert yaml.load(source, Loader, duplicate_key_policy="last") == {
        "timeout": 2,
    }
    assert yaml.load(
        source,
        Loader,
        duplicate_key_policy=yaml.DuplicateKeyPolicy.FIRST,
    ) == {"timeout": 1}
    assert yaml.load(
        source,
        Loader,
        duplicate_key_policy=yaml.DuplicateKeyPolicy.LAST,
    ) == {"timeout": 2}


def test_safe_load_and_safe_load_all_accept_policy():
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load("timeout: 1\ntimeout: 2\n", duplicate_key_policy="reject")

    with pytest.raises(yaml.constructor.ConstructorError):
        list(yaml.safe_load_all(
            "timeout: 1\ntimeout: 2\n",
            duplicate_key_policy=yaml.DuplicateKeyPolicy.REJECT,
        ))


@pytest.mark.parametrize("Loader", loader_classes())
def test_explicit_key_can_override_merged_key(Loader):
    source = """
base: &base {x: inherited}
target:
  <<: *base
  x: explicit
"""

    assert yaml.load(source, Loader, duplicate_key_policy="reject") == {
        "base": {"x": "inherited"},
        "target": {"x": "explicit"},
    }


@pytest.mark.parametrize("Loader", loader_classes())
def test_multiple_merges_keep_merge_precedence(Loader):
    source = """
first: &first {x: 1, y: 1}
second: &second {x: 2, z: 2}
target:
  <<: [*first, *second]
  z: explicit
other:
  <<: *second
  <<: *first
"""

    result = yaml.load(source, Loader, duplicate_key_policy="reject")

    assert result["target"] == {"x": 1, "y": 1, "z": "explicit"}
    assert result["other"] == {"x": 2, "y": 1, "z": 2}


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_key_policy_uses_constructed_key_equality(Loader):
    source = "true: bool\n1: int\n"

    assert yaml.load(source, Loader, duplicate_key_policy="first") == {
        True: "bool",
    }
    assert yaml.load(source, Loader, duplicate_key_policy="last") == {
        True: "int",
    }
    with pytest.raises(yaml.constructor.ConstructorError) as excinfo:
        yaml.load(source, Loader, duplicate_key_policy="reject")
    assert error_reports_both_duplicate_key_locations(excinfo.value)


@pytest.mark.parametrize("Loader", loader_classes())
def test_unhashable_key_remains_constructor_error(Loader):
    with pytest.raises(yaml.constructor.ConstructorError) as excinfo:
        yaml.load("[x]: 1\n[x]: 2\n", Loader, duplicate_key_policy="reject")

    assert "found unhashable key" in str(excinfo.value)


@pytest.mark.parametrize("Loader", loader_classes())
def test_anchor_reuse_is_not_mutated_by_merge_detection(Loader):
    source = """
base: &base {x: base}
first:
  nested: &nested
    <<: *base
    x: first
second:
  nested:
    <<: *base
    x: second
third:
  <<: *nested
"""

    result = yaml.load(source, Loader, duplicate_key_policy="reject")

    assert result["first"]["nested"] == {"x": "first"}
    assert result["second"]["nested"] == {"x": "second"}
    assert result["third"] == {"x": "first"}


@pytest.mark.parametrize("Loader", loader_classes())
def test_safe_load_rejects_duplicate_in_inline_merge_parent(Loader):
    source = """
target:
  <<: {x: 1, x: 2}
  y: 3
"""

    with pytest.raises(yaml.constructor.ConstructorError) as excinfo:
        yaml.load(source, Loader, duplicate_key_policy="reject")

    error = excinfo.value
    assert error.context_mark.line == 2
    assert error.problem_mark.line == 2
    assert "mapping path: <root>.target.<<" in str(error)


def error_reports_both_duplicate_key_locations(error):
    return (
        error.context_mark is not None
        and error.problem_mark is not None
        and error.context_mark.index != error.problem_mark.index
    )
