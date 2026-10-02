import pytest

import yaml


COLOR_TAG = "tag:example.com/biz/color"
ITEMS_TAG = "tag:example.com/biz/items"
LABEL_TAG = "tag:example.com/biz/label"
NODE_TAG = "tag:example.com/biz/node"


class Color:
    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, Color) and self.value == other.value


def preserving_classes():
    classes = [
        (yaml.SafePreservingLoader, yaml.SafePreservingDumper)
    ]
    if hasattr(yaml, "CSafePreservingLoader"):
        classes.append(
            (yaml.CSafePreservingLoader, yaml.CSafePreservingDumper)
        )
    return classes


def color_loader(base):
    class ColorLoader(base):
        pass

    ColorLoader.add_constructor(
        COLOR_TAG, lambda loader, node: Color(loader.construct_scalar(node))
    )
    return ColorLoader


def color_dumper(base):
    class ColorDumper(base):
        pass

    ColorDumper.add_representer(
        Color,
        lambda dumper, data: dumper.represent_scalar(COLOR_TAG, data.value)
    )
    return ColorDumper


@pytest.mark.parametrize("Loader,Dumper", preserving_classes())
def test_safe_preserving_roundtrip(Loader, Dumper):
    source = """
%TAG !biz! tag:example.com/biz/
---
known: &known !biz!color red
using_known: *known
known_items: &known_items
- one
known_items_again: *known_items
shared: &shared !biz!items
- !biz!label hello
- plain: 1
same: *shared
shared_label: &shared_label !biz!label retained
same_label: *shared_label
loop: &loop !biz!node
  label: !biz!label world
  again: *loop
danger:
  apply: !!python/object/apply:os.system [echo unsafe]
  new: !!python/object/new:os.system [echo unsafe]
"""

    data = yaml.load(source, Loader=color_loader(Loader))

    assert isinstance(data["known"], Color)
    assert data["known"].value == "red"
    assert data["using_known"] is data["known"]
    assert data["known_items_again"] is data["known_items"]

    shared = data["shared"]
    assert isinstance(shared, yaml.TaggedValue)
    assert shared.tag == ITEMS_TAG
    assert shared.value[0] == yaml.TaggedValue(LABEL_TAG, "hello")
    assert shared.value[1] == {"plain": 1}
    assert data["same"] is shared

    loop = data["loop"]
    assert isinstance(loop, yaml.TaggedValue)
    assert loop.tag == NODE_TAG
    assert loop.value["label"] == yaml.TaggedValue(LABEL_TAG, "world")
    assert loop.value["again"] is loop

    assert data["danger"]["apply"] == yaml.TaggedValue(
        "tag:yaml.org,2002:python/object/apply:os.system",
        ["echo unsafe"],
    )
    assert data["danger"]["new"] == yaml.TaggedValue(
        "tag:yaml.org,2002:python/object/new:os.system",
        ["echo unsafe"],
    )

    rendered = yaml.dump(
        data,
        Dumper=color_dumper(Dumper),
        tags={"!biz!": "tag:example.com/biz/"},
        sort_keys=False,
    )
    restored = yaml.load(rendered, Loader=color_loader(Loader))

    assert restored["known"] == Color("red")
    assert restored["using_known"] is restored["known"]
    assert restored["known_items_again"] is restored["known_items"]
    assert restored["same"] is restored["shared"]
    assert restored["same_label"] is restored["shared_label"]
    assert restored["shared_label"] == yaml.TaggedValue(LABEL_TAG, "retained")
    assert restored["loop"].value["again"] is restored["loop"]
    assert restored["shared"].tag == ITEMS_TAG
    assert restored["loop"].tag == NODE_TAG
    assert isinstance(restored["danger"]["apply"], yaml.TaggedValue)
    assert isinstance(restored["danger"]["new"], yaml.TaggedValue)


def test_tag_directives_are_scoped_to_each_document():
    source = """
%TAG !biz! tag:example.com/one/
--- !biz!item first
...
%TAG !biz! tag:example.com/two/
--- !biz!item second
"""

    documents = list(yaml.safe_preserving_load_all(source))

    assert documents == [
        yaml.TaggedValue("tag:example.com/one/item", "first"),
        yaml.TaggedValue("tag:example.com/two/item", "second"),
    ]

    rendered = yaml.safe_preserving_dump_all(
        documents,
        explicit_start=True,
        tags=[
            {"!one!": "tag:example.com/one/"},
            {"!two!": "tag:example.com/two/"},
        ],
    )

    assert "%TAG !one! tag:example.com/one/" in rendered
    assert "%TAG !two! tag:example.com/two/" in rendered
    assert "--- !one!item 'first'" in rendered
    assert "--- !two!item 'second'" in rendered
    redumped = list(yaml.safe_preserving_load_all(rendered))
    assert redumped == documents


def test_safe_load_and_dump_preserve_tags_option():
    source = "value: !example.com/name content\n"

    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(source)

    data = yaml.safe_load(source, preserve_tags=True)
    assert data == {
        "value": yaml.TaggedValue("!example.com/name", "content")
    }

    rendered = yaml.safe_dump(data, preserve_tags=True)
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load(rendered)
    assert yaml.safe_load(rendered, preserve_tags=True) == data
