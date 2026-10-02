import time

import pytest

import yaml
from yaml import ResourceLimitError
from yaml.loader import SafeLoader


# Small-input builders. Every document below is a few hundred bytes at most;
# enforcing a budget must stop parsing before any large allocation happens.

def nested(depth):
    # A sequence nested `depth` levels deep around a single scalar.
    return "[" * depth + "0" + "]" * depth


def nested_mapping(depth):
    return "{a: " * depth + "0" + "}" * depth


def aliased(count):
    # One anchored scalar referenced `count` times via a flow sequence, so
    # the only unique nodes are the enclosing mapping, one key, one sequence,
    # one anchored scalar, and the alias references (which are not nodes).
    return "a: &a 0\nseq: [" + ", ".join("*a" for _ in range(count)) + "]\n"


def aliased_stream(documents, per_document):
    return "---\n".join(aliased(per_document) for _ in range(documents))


def nodes_doc(count):
    # A sequence with `count` scalar items: count + 1 unique nodes.
    return "[" + ", ".join(str(index % 10) for index in range(count)) + "]"


def scalar_doc(length, style="plain"):
    value = "x" * length
    if style == "plain":
        return value
    if style == "single":
        return "'" + value + "'"
    if style == "double":
        return '"' + value + '"'
    if style == "literal":
        return "|-\n" + "  " + value
    if style == "folded":
        return ">-\n" + "  " + value
    raise ValueError(style)


def limits(**overrides):
    # Disable everything except the budget under test, unless explicitly set.
    base = dict(max_depth=None, max_scalar_length=None, max_nodes=None,
                max_aliases=None, stream_max_scalar_length=None,
                stream_max_nodes=None, stream_max_aliases=None)
    base.update(overrides)
    return yaml.ResourceLimits(**base)


# ---------------------------------------------------------------------------
# Nesting depth
# ---------------------------------------------------------------------------

def test_depth_boundary_is_allowed():
    assert yaml.safe_load(nested(5), limits=limits(max_depth=5)) == [[[[[0]]]]]


@pytest.mark.parametrize("builder", [nested, nested_mapping])
def test_depth_one_over_limit_rejected(builder):
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(builder(6), limits=limits(max_depth=5))
    error = excinfo.value
    assert error.category == ResourceLimitError.CATEGORY_DEPTH
    assert error.scope == "document"
    assert error.limit == 5
    assert error.usage == 6
    assert error.problem_mark is not None


def test_deep_nesting_tiny_input_is_fast():
    start = time.monotonic()
    with pytest.raises(ResourceLimitError) as excinfo:
        # 10 000 levels expressed in 20 001 bytes; must bail out immediately.
        yaml.safe_load(nested(10000), limits=limits(max_depth=32))
    elapsed = time.monotonic() - start
    assert excinfo.value.category == ResourceLimitError.CATEGORY_DEPTH
    assert excinfo.value.usage == 33
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# Scalar length (charged during scanning)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("style", ["plain", "single", "double", "literal",
                                   "folded"])
def test_scalar_length_boundary(style):
    assert yaml.safe_load(scalar_doc(10, style),
                          limits=limits(max_scalar_length=10)) == "x" * 10


@pytest.mark.parametrize("style", ["plain", "single", "double", "literal",
                                   "folded"])
def test_scalar_length_over_limit(style):
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(scalar_doc(11, style),
                       limits=limits(max_scalar_length=10))
    error = excinfo.value
    assert error.category == ResourceLimitError.CATEGORY_SCALAR_LENGTH
    assert error.scope == "document"
    assert error.limit == 10
    assert error.usage == 11
    assert error.problem_mark is not None


def test_long_scalar_tiny_source_is_fast():
    start = time.monotonic()
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(scalar_doc(1_000_000, "literal"),
                       limits=limits(max_scalar_length=64))
    elapsed = time.monotonic() - start
    assert excinfo.value.category == ResourceLimitError.CATEGORY_SCALAR_LENGTH
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# Unique nodes
# ---------------------------------------------------------------------------

def test_nodes_boundary_is_allowed():
    # 9 items + the enclosing sequence = 10 unique nodes.
    assert yaml.safe_load(nodes_doc(9), limits=limits(max_nodes=10)) == \
        list(range(9))


def test_nodes_over_limit_rejected():
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(nodes_doc(10), limits=limits(max_nodes=10))
    error = excinfo.value
    assert error.category == ResourceLimitError.CATEGORY_NODES
    assert error.scope == "document"
    assert error.limit == 10
    assert error.usage == 11


def test_aliases_do_not_count_as_nodes():
    # 5 unique nodes (mapping, two keys, sequence, anchored scalar) plus 50
    # alias references; a node budget of 5 must accept the document.
    doc = aliased(50)
    result = yaml.safe_load(doc, limits=limits(max_nodes=5, max_aliases=None))
    assert result["seq"] == [0] * 50
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(doc, limits=limits(max_nodes=4, max_aliases=None))
    assert excinfo.value.category == ResourceLimitError.CATEGORY_NODES


# ---------------------------------------------------------------------------
# Alias references (metered separately, iteratively)
# ---------------------------------------------------------------------------

def test_aliases_boundary_is_allowed():
    result = yaml.safe_load(aliased(5), limits=limits(max_aliases=5))
    assert result["seq"] == [0] * 5


def test_aliases_over_limit_rejected():
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(aliased(6), limits=limits(max_aliases=5))
    error = excinfo.value
    assert error.category == ResourceLimitError.CATEGORY_ALIASES
    assert error.scope == "document"
    assert error.limit == 5
    assert error.usage == 6
    assert error.problem_mark is not None


def test_many_aliases_tiny_input_is_fast():
    # Billion-laughs style fanout written compactly.
    fanout = (
        "a: &a 0\n"
        "b: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
        "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b,*b]\n"
        "d: [*c,*c,*c,*c,*c,*c,*c,*c,*c,*c]\n"
    )
    start = time.monotonic()
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(fanout, limits=limits(max_aliases=25))
    elapsed = time.monotonic() - start
    assert excinfo.value.category == ResourceLimitError.CATEGORY_ALIASES
    assert elapsed < 2.0


def test_cyclic_alias_does_not_recurse_in_budget_check():
    # Self referencing document with many alias uses; the check itself must
    # not walk the (cyclic) node graph.
    doc = "&a [*a, *a, *a, *a]"
    start = time.monotonic()
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(doc, limits=limits(max_aliases=2))
    elapsed = time.monotonic() - start
    assert excinfo.value.category == ResourceLimitError.CATEGORY_ALIASES
    assert elapsed < 2.0
    # And a cycle within budget loads fine.
    result = yaml.safe_load(doc, limits=limits())
    assert result[0] is result


# ---------------------------------------------------------------------------
# Per-document vs whole-stream budgets (load_all)
# ---------------------------------------------------------------------------

def test_per_document_alias_budget_resets_between_documents():
    stream = aliased_stream(documents=3, per_document=4)
    lim = limits(max_aliases=4, stream_max_aliases=None)
    documents = list(yaml.safe_load_all(stream, limits=lim))
    assert len(documents) == 3
    assert all(doc["seq"] == [0] * 4 for doc in documents)


def test_stream_alias_budget_accumulates_across_documents():
    stream = aliased_stream(documents=3, per_document=4)
    lim = limits(max_aliases=4, stream_max_aliases=9)
    documents = yaml.safe_load_all(stream, limits=lim)
    next(documents)
    next(documents)
    with pytest.raises(ResourceLimitError) as excinfo:
        next(documents)
    error = excinfo.value
    assert error.category == ResourceLimitError.CATEGORY_ALIASES
    assert error.scope == "stream"
    assert error.limit == 9
    assert error.usage == 10


def test_stream_node_budget_accumulates():
    stream = "\n---\n".join(nodes_doc(3) for _ in range(3))
    # 4 unique nodes per document (sequence + 3 items).
    lim = limits(max_nodes=4, stream_max_nodes=9)
    documents = yaml.safe_load_all(stream, limits=lim)
    next(documents)
    next(documents)
    with pytest.raises(ResourceLimitError) as excinfo:
        next(documents)
    assert excinfo.value.scope == "stream"
    assert excinfo.value.category == ResourceLimitError.CATEGORY_NODES
    assert excinfo.value.usage == 10


def test_stream_scalar_budget_accumulates():
    stream = "\n---\n".join(scalar_doc(4) for _ in range(3))
    lim = limits(max_scalar_length=4, stream_max_scalar_length=9)
    documents = yaml.safe_load_all(stream, limits=lim)
    next(documents)
    next(documents)
    with pytest.raises(ResourceLimitError) as excinfo:
        next(documents)
    assert excinfo.value.scope == "stream"
    assert excinfo.value.category == ResourceLimitError.CATEGORY_SCALAR_LENGTH
    assert excinfo.value.usage == 12


def test_dispose_resets_stream_budget():
    loader = SafeLoader(aliased(3), limits=limits(max_aliases=None,
                                                  stream_max_aliases=None))
    loader.get_single_data()
    assert loader._resource_budget.stream_aliases == 3
    loader.dispose()
    assert loader._resource_budget.stream_aliases == 0


# ---------------------------------------------------------------------------
# Temporary-state release on failure
# ---------------------------------------------------------------------------

def test_anchor_table_released_after_alias_budget_error():
    loader = SafeLoader(aliased(3), limits=limits(max_aliases=1))
    with pytest.raises(ResourceLimitError):
        loader.get_single_data()
    # Composer per-document state must not retain the partial node graph.
    assert loader.anchors == {}


def test_constructor_state_released_after_depth_error():
    loader = SafeLoader(nested(10), limits=limits(max_depth=4))
    with pytest.raises(ResourceLimitError):
        loader.get_single_data()
    assert loader.constructed_objects == {}
    assert loader.recursive_objects == {}
    assert loader.state_generators == []


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_unlimited_limits_never_trigger():
    assert yaml.safe_load(nested(200), limits=yaml.ResourceLimits.unlimited())
    assert yaml.safe_load(aliased(200),
                          limits=yaml.ResourceLimits.unlimited())
    assert yaml.safe_load(
        scalar_doc(100000),
        limits=yaml.ResourceLimits.unlimited()) == "x" * 100000


def test_default_limits_block_pathological_input():
    # Defaults are finite but generous; a clearly pathological tiny document
    # must still be rejected quickly.
    start = time.monotonic()
    with pytest.raises(ResourceLimitError) as excinfo:
        yaml.safe_load(nested(10000))
    assert excinfo.value.category == ResourceLimitError.CATEGORY_DEPTH
    assert time.monotonic() - start < 2.0


def test_limits_must_be_resource_limits_instance():
    with pytest.raises(TypeError):
        SafeLoader("x", limits=123)


def test_unsafe_loaders_unaffected_by_default():
    # The generic Loader keeps unlimited behaviour; budgets only apply to the
    # pure-Python safe loading path.
    assert yaml.load(nested(200), Loader=yaml.Loader) is not None
