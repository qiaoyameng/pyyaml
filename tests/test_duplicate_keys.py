import pytest

import yaml


def loader_classes():
    classes = [yaml.SafeLoader]
    if hasattr(yaml, "CSafeLoader"):
        classes.append(yaml.CSafeLoader)
    return classes


@pytest.mark.parametrize("Loader", loader_classes())
@pytest.mark.parametrize(
    ("policy", "value"),
    [
        (yaml.DuplicateKeys.LAST, 2),
        ("last", 2),
        (yaml.DuplicateKeys.FIRST, 1),
        ("first", 1),
        ("keep-first", 1),
    ],
)
def test_duplicate_key_policy_keeps_requested_value(Loader, policy, value):
    result = yaml.load("timeout: 1\ntimeout: 2\n", Loader, duplicate_keys=policy)

    assert result == {"timeout": value}


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_key_policy_reports_first_and_second_locations(Loader):
    source = "outer:\n  inner:\n    timeout: 1\n    timeout: 2\n"

    with pytest.raises(yaml.DuplicateKeyError) as exc_info:
        yaml.load(source, Loader, duplicate_keys=yaml.DuplicateKeys.RAISE)

    error = exc_info.value
    assert (error.context_mark.line, error.context_mark.column) == (2, 4)
    assert (error.problem_mark.line, error.problem_mark.column) == (3, 4)
    assert error.note == "mapping path: $.outer.inner"
    assert "timeout" in error.context


@pytest.mark.parametrize("Loader", loader_classes())
def test_constructed_equal_keys_conflict(Loader):
    with pytest.raises(yaml.DuplicateKeyError) as exc_info:
        yaml.load(
            "true: boolean\n1: number\n",
            Loader,
            duplicate_keys="reject",
        )

    assert (exc_info.value.context_mark.line,
            exc_info.value.problem_mark.line) == (0, 1)


@pytest.mark.parametrize("Loader", loader_classes())
def test_unhashable_key_keeps_constructor_error(Loader):
    with pytest.raises(yaml.constructor.ConstructorError) as exc_info:
        yaml.load("[]: value\n", Loader, duplicate_keys="raise")

    assert "found unhashable key" in str(exc_info.value)


@pytest.mark.parametrize("Loader", loader_classes())
def test_explicit_value_key_duplicates_are_detected(Loader):
    with pytest.raises(yaml.DuplicateKeyError) as exc_info:
        yaml.load("=: 1\n=: 2\n", Loader, duplicate_keys="raise")

    assert exc_info.value.note == "mapping path: $"


@pytest.mark.parametrize("Loader", loader_classes())
def test_explicit_merge_override_is_not_a_duplicate(Loader):
    source = "base: &base {x: 1}\ntarget: {<<: *base, x: 2}\n"

    result = yaml.load(source, Loader, duplicate_keys="raise")

    assert result["target"] == {"x": 2}


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_inherited_keys_are_not_duplicates(Loader):
    source = (
        "first: &first {x: 1, y: 1}\n"
        "second: &second {x: 2, z: 2}\n"
        "target: {<<: [*first, *second], w: 3}\n"
    )

    result = yaml.load(source, Loader, duplicate_keys="raise")

    assert result["target"] == {"x": 1, "y": 1, "z": 2, "w": 3}


@pytest.mark.parametrize("Loader", loader_classes())
def test_repeated_merge_sources_are_not_duplicates(Loader):
    source = (
        "base: &base {x: 1}\n"
        "target:\n  <<: [*base, *base]\n  <<: *base\n  y: 2\n"
    )

    result = yaml.load(source, Loader, duplicate_keys="raise")

    assert result["target"] == {"x": 1, "y": 2}


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_inside_nested_merge_source_is_rejected(Loader):
    source = (
        "base: &base\n  x: 1\n  x: 2\n"
        "target:\n  <<: *base\n  y: 3\n"
    )

    with pytest.raises(yaml.DuplicateKeyError) as exc_info:
        yaml.load(source, Loader, duplicate_keys="raise")

    assert exc_info.value.note == "mapping path: $.base"
    assert exc_info.value.context_mark.line == 1
    assert exc_info.value.problem_mark.line == 2


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_inside_anonymous_merge_source_is_rejected(Loader):
    source = "target:\n  <<:\n    - x: 1\n      x: 2\n  y: 3\n"

    with pytest.raises(yaml.DuplicateKeyError) as exc_info:
        yaml.load(source, Loader, duplicate_keys="raise")

    assert exc_info.value.note == "mapping path: $.target.<<[0]"
    assert exc_info.value.context_mark.line == 2
    assert exc_info.value.problem_mark.line == 3


@pytest.mark.parametrize("Loader", loader_classes())
def test_duplicate_in_merge_only_anchor_reports_anchor_path(Loader):
    source = (
        "base: &base\n  x: 1\n  x: 2\n"
        "target:\n  <<: *base\n  y: 3\n"
        "unused: *base\n"
    )

    with pytest.raises(yaml.DuplicateKeyError) as exc_info:
        yaml.load(source, Loader, duplicate_keys="raise")

    assert exc_info.value.note == "mapping path: $.base"


@pytest.mark.parametrize("Loader", loader_classes())
def test_reusing_anchor_does_not_mutate_later_result(Loader):
    source = (
        "base: &base\n  x: 1\n"
        "first: {<<: *base, y: 2}\n"
        "second: {<<: *base, z: 3}\n"
    )

    result = yaml.load(source, Loader, duplicate_keys="raise")

    assert result["first"] == {"x": 1, "y": 2}
    assert result["second"] == {"x": 1, "z": 3}


@pytest.mark.parametrize("Loader", loader_classes())
def test_anchor_with_duplicate_is_rejected_each_time_it_is_loaded(Loader):
    source = (
        "base: &base\n  x: 1\n  x: 2\n"
        "first: {<<: *base, y: 3}\n"
        "second: {<<: *base, z: 4}\n"
    )

    for _ in range(2):
        with pytest.raises(yaml.DuplicateKeyError) as exc_info:
            yaml.load(source, Loader, duplicate_keys="raise")
        assert exc_info.value.note == "mapping path: $.base"


def test_safe_load_reports_invalid_policy():
    with pytest.raises(ValueError, match="invalid duplicate key policy"):
        yaml.safe_load("x: 1\n", duplicate_keys="replace")


def test_safe_load_all_uses_duplicate_key_policy():
    documents = list(yaml.safe_load_all(
        "timeout: 1\ntimeout: 2\n---\nx: 1\n",
        duplicate_keys=yaml.DuplicateKeys.FIRST,
    ))

    assert documents == [{"timeout": 1}, {"x": 1}]


def test_duplicate_key_policy_alias_is_exported():
    assert yaml.DuplicateKeyPolicy is yaml.DuplicateKeys
