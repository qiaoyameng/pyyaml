import pytest

import yaml


SOURCE = """
%TAG !biz! tag:example.test/biz/
---
scalar: !biz!mode production
sequence: &sequence !biz!ports
  - 8000
  - 8001
mapping: &mapping !biz!config
  name: primary
  ports: *sequence
sequence_alias: *sequence
mapping_alias: *mapping
known_scalar: !!str 123
known_sequence: &known_sequence !!seq [1, 2]
known_sequence_alias: *known_sequence
known_mapping: &known_mapping !!map {enabled: true}
known_mapping_alias: *known_mapping
object_attack:
  !!python/object/apply:os.system
  args: [echo exploited]
"""


def test_preserves_unknown_tag_data_and_registered_constructor_priority():
    data = yaml.safe_load(SOURCE, preserve_tags=True)

    scalar = data["scalar"]
    assert scalar.tag == "tag:example.test/biz/mode"
    assert scalar.value == "production"
    assert data["sequence"].tag == "tag:example.test/biz/ports"
    assert data["sequence"].value == [8000, 8001]
    assert data["mapping"].tag == "tag:example.test/biz/config"
    assert data["mapping"].value == {
        "name": "primary",
        "ports": data["sequence"],
    }
    assert data["known_scalar"] == "123"
    assert data["known_sequence_alias"] is data["known_sequence"]
    assert data["known_mapping_alias"] is data["known_mapping"]
    assert isinstance(data["object_attack"], yaml.TaggedValue)
    assert data["object_attack"].tag == (
        "tag:yaml.org,2002:python/object/apply:os.system")
    assert data["object_attack"].value == {"args": ["echo exploited"]}


def test_roundtrip_preserves_tags_and_node_identity():
    data = yaml.safe_load(SOURCE, preserve_tags=True)
    output = yaml.safe_dump(data, preserve_tags=True, sort_keys=False)
    reloaded = yaml.safe_load(output, preserve_tags=True)

    scalar = reloaded["scalar"]
    assert scalar.tag == "tag:example.test/biz/mode"
    assert scalar.value == "production"
    assert reloaded["sequence_alias"] is reloaded["sequence"]
    assert reloaded["mapping_alias"] is reloaded["mapping"]
    assert reloaded["mapping"].value["ports"] is reloaded["sequence"]
    assert reloaded["known_scalar"] == "123"
    assert reloaded["known_sequence_alias"] is reloaded["known_sequence"]
    assert reloaded["known_mapping_alias"] is reloaded["known_mapping"]
    assert isinstance(reloaded["object_attack"], yaml.TaggedValue)
    assert "!<tag:example.test/biz/mode>" in output
    assert "!!python/object/apply:os.system" in output


def test_preserves_shared_scalar_alias():
    source = """
items:
  - &value !choice one
  - *value
"""
    data = yaml.safe_load(source, preserve_tags=True)

    assert data["items"][0] is data["items"][1]

    output = yaml.safe_dump(data, preserve_tags=True, sort_keys=False)
    reloaded = yaml.safe_load(output, preserve_tags=True)

    assert reloaded["items"][0] is reloaded["items"][1]


def test_preserves_recursive_node_identity():
    source = """
self: &node !recursive
  child: *node
"""
    data = yaml.safe_load(source, preserve_tags=True)
    node = data["self"]

    assert node.value["child"] is node

    output = yaml.safe_dump(data, preserve_tags=True, sort_keys=False)
    reloaded = yaml.safe_load(output, preserve_tags=True)
    reloaded_node = reloaded["self"]

    assert reloaded_node.value["child"] is reloaded_node


def test_preserves_recursive_sequence_identity():
    source = """
sequence: &node !recursive-sequence
  - *node
"""
    data = yaml.safe_load(source, preserve_tags=True)
    node = data["sequence"]

    assert node.value[0] is node

    output = yaml.safe_dump(data, preserve_tags=True, sort_keys=False)
    reloaded = yaml.safe_load(output, preserve_tags=True)
    reloaded_node = reloaded["sequence"]

    assert reloaded_node.value[0] is reloaded_node


def test_registered_constructor_takes_precedence():
    class RegisteredLoader(yaml.TagPreservingSafeLoader):
        pass

    RegisteredLoader.add_constructor(
        "!registered",
        lambda loader, node: {"raw": loader.construct_scalar(node)})

    data = yaml.load("!registered hello", Loader=RegisteredLoader)

    assert data == {"raw": "hello"}


@pytest.mark.parametrize("tag", [
    "!!python/object:os.system",
    "!!python/object/new:os.system",
    "!!python/object/apply:os.system",
])
def test_python_object_tags_become_data(tag):
    data = yaml.safe_load(f"{tag}\nargs: []\n", preserve_tags=True)

    assert isinstance(data, yaml.TaggedValue)
    assert data.tag.endswith(":os.system")
    assert data.value == {"args": []}


def test_tag_directives_are_scoped_per_document():
    source = """
%TAG !local! tag:first.example/
--- !local!name first
...
%TAG !local! tag:second.example/
--- !local!name second
...
--- !undefined name
"""
    documents = list(yaml.safe_load_all(source, preserve_tags=True))

    assert documents[0].tag == "tag:first.example/name"
    assert documents[1].tag == "tag:second.example/name"
    assert documents[2].tag == "!undefined"

    with pytest.raises(yaml.YAMLError):
        list(yaml.safe_load_all(
            """
%TAG !local! tag:first.example/
--- !local!name first
...
--- !local!name missing-directive
""",
            preserve_tags=True,
        ))


def test_default_safe_loader_rejects_unknown_tags():
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load("!unknown value")


def test_default_safe_dumper_rejects_tagged_values():
    with pytest.raises(yaml.YAMLError):
        yaml.safe_dump(yaml.TaggedValue("!unknown", "value"))
