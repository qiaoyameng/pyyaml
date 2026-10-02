import pytest

import yaml
from yaml import Key, Index, SourceIndex, format_path


CONFIG = """\
defaults: &defaults
  host: example.com
  port: 8080
  tags: [a, b]
first:
  <<: *defaults
  port: 9001
second: *defaults
"""


def linecol(text, needle, occurrence=1):
    """1-based (line, column) of the n-th occurrence of needle."""
    lines = text.splitlines()
    seen = 0
    for lineno, line in enumerate(lines, start=1):
        start = 0
        while True:
            column = line.find(needle, start)
            if column < 0:
                break
            seen += 1
            if seen == occurrence:
                return lineno, column + 1
            start = column + 1
    raise AssertionError("%r not found" % needle)


def test_merge_and_alias_sources():
    data, index = yaml.safe_load_with_index(CONFIG)

    # Local override keeps its own position.
    entry = index.lookup("first", "port")
    assert entry.kind == "value"
    assert entry.via is None
    assert (entry.defined_at.line, entry.defined_at.column) == linecol(CONFIG, "9001")
    assert (entry.key_at.line, entry.key_at.column) == linecol(CONFIG, "port: 9001")

    # Merged field: defined in the anchor, used at the merge key.
    entry = index.lookup("first", "host")
    assert entry.via == "merge"
    assert (entry.defined_at.line, entry.defined_at.column) == linecol(CONFIG, "example.com")
    assert (entry.key_at.line, entry.key_at.column) == linecol(CONFIG, "host:")
    assert (entry.used_at.line, entry.used_at.column) == linecol(CONFIG, "<<:")
    assert entry.target == SourceIndex.path("defaults", "host")

    # Merged collection: referenced, not re-indexed under the merge site.
    entry = index.lookup("first", "tags")
    assert entry.kind == "reference"
    assert entry.via == "merge"
    assert entry.target == SourceIndex.path("defaults", "tags")
    assert SourceIndex.path("first", "tags", 0) not in index

    # Alias reuse: definition and use locations, no duplicated subtree.
    entry = index.lookup("second")
    assert entry.kind == "reference"
    assert entry.via == "alias"
    assert entry.anchor == "defaults"
    assert (entry.defined_at.line, entry.defined_at.column) == linecol(CONFIG, "&defaults")
    assert (entry.used_at.line, entry.used_at.column) == linecol(CONFIG, "*defaults", occurrence=2)
    assert entry.target == SourceIndex.path("defaults")
    assert SourceIndex.path("second", "host") not in index

    # Definition site of the anchor itself.
    entry = index.lookup("defaults")
    assert entry.kind == "value"
    assert entry.anchor == "defaults"

    # Sequence items are indexed by position.
    entry = index.lookup("defaults", "tags", 1)
    assert (entry.defined_at.line, entry.defined_at.column) == linecol(CONFIG, "b]")


def test_object_identity_matches_safe_load():
    data, _ = yaml.safe_load_with_index(CONFIG)
    plain = yaml.safe_load(CONFIG)

    assert data == plain
    # Shared objects stay shared exactly like plain safe_load.
    assert (data["second"] is data["defaults"]) == (plain["second"] is plain["defaults"])
    assert (data["first"]["tags"] is data["defaults"]["tags"]) == \
            (plain["first"]["tags"] is plain["defaults"]["tags"])
    assert data["second"] is data["defaults"]
    assert data["first"]["tags"] is data["defaults"]["tags"]


def test_recursive_alias_is_a_finite_reference():
    data, index = yaml.safe_load_with_index("&a\n- 1\n- *a\n")
    assert data[1] is data
    assert yaml.safe_load("&a\n- 1\n- *a\n")[1] is not data  # independent loads

    entry = index[(Index(1),)]
    assert entry.kind == "reference"
    assert entry.via == "alias"
    assert entry.target == ()
    # The recursion is expressed by the reference alone: no deeper entries.
    assert len(index) == 3
    assert format_path(entry.target) == "$"


def test_multi_document_indices():
    source = "a: 1\n---\nb: 2\n---\n- x\n"
    results = list(yaml.safe_load_all_with_index(source))
    assert [data for data, _ in results] == list(yaml.safe_load_all(source))
    for number, (data, index) in enumerate(results):
        assert index.document == number
        for entry in index:
            assert entry.document == number
            assert entry.defined_at.document == number
    assert (results[1][1].lookup("b").defined_at.line,
            results[1][1].lookup("b").defined_at.column) == linecol(source, "2")


def test_path_segments_distinguish_keys_from_indices():
    data, index = yaml.safe_load_with_index("0: zero\nitems: [x]\n")
    assert data == {0: "zero", "items": ["x"]}
    assert Key(0) != Index(0)
    assert (Key(0),) in index.entries
    assert (Index(0),) not in index.entries
    assert (Key("items"), Index(0)) in index.entries
    assert format_path((Key("items"), Index(0))) == "$.items[0]"


def test_single_document_required():
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load_with_index("a: 1\n---\nb: 2\n")


def test_empty_stream():
    data, index = yaml.safe_load_with_index("")
    assert data is None
    assert len(index) == 0
