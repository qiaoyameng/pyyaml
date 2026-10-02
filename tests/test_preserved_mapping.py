import pytest

import yaml


SEQUENCE_KEY_DOC = """
? [1, 2, 3]
: sequence-key
? {a: 1, b: 2}
: mapping-key
scalar: value
"""

DUPLICATE_KEY_DOC = """
x: first
x: second
x: third
1: int-key
true: bool-key
1.0: float-key
'1': string-key
"""

SHARED_NODE_DOC = """
shared: &shared
  - 1
  - two
  - ? [deep, key]
    : deep-value
? *shared
: shared-as-key
copy: *shared
"""


def load(text):
    return yaml.safe_load(text, preserve=True)


def test_sequence_and_mapping_keys():
    data = load(SEQUENCE_KEY_DOC)
    assert isinstance(data, yaml.PreservedMapping)
    assert len(data) == 3

    keys = data.keys()
    assert type(keys[0]) is list
    assert keys[0] == [1, 2, 3]
    assert type(keys[1]) is yaml.PreservedMapping
    assert keys[1] == yaml.PreservedMapping([('a', 1), ('b', 2)])
    assert type(keys[2]) is str

    assert data[[1, 2, 3]] == 'sequence-key'
    assert data[{'a': 1, 'b': 2}] == 'mapping-key'
    assert data['scalar'] == 'value'


def test_nested_complex_key_preserves_types():
    data = load(SEQUENCE_KEY_DOC)
    mapping_key = data.keys()[1]
    assert type(mapping_key['a']) is int
    complex_nested = load(SHARED_NODE_DOC)
    deep_list = complex_nested['shared']
    assert deep_list[2] == yaml.PreservedMapping([(['deep', 'key'], 'deep-value')])
    assert type(deep_list[0]) is int
    assert type(deep_list[1]) is str


def test_duplicate_scalar_keys_are_kept():
    data = load(DUPLICATE_KEY_DOC)
    assert len(data) == 7

    entries = data.entries
    assert [(key, value) for key, value in entries if key == 'x'] == [
        ('x', 'first'), ('x', 'second'), ('x', 'third'),
    ]
    # lookup follows YAML "last wins" semantics
    assert data['x'] == 'third'

    # Python-equal but YAML-typed-different keys stay distinct
    assert data[1] == 'int-key'
    assert data[True] == 'bool-key'
    assert data[1.0] == 'float-key'
    assert data['1'] == 'string-key'
    assert [type(key) for key in data.keys()] == [
        str, str, str, int, bool, float, str,
    ]


def test_key_equality_distinguishes_yaml_types():
    assert 1 in load(DUPLICATE_KEY_DOC)
    assert True in load(DUPLICATE_KEY_DOC)

    data = yaml.PreservedMapping()
    data[1] = 'int'
    with pytest.raises(KeyError):
        data[True]
    data[True] = 'bool'
    assert len(data) == 2
    assert data[1] == 'int'
    assert data[True] == 'bool'
    assert yaml.yaml_key_equal(1, 1)
    assert not yaml.yaml_key_equal(1, True)
    assert not yaml.yaml_key_equal(1, 1.0)
    assert yaml.yaml_key_equal([1, [2, 3]], [1, [2, 3]])
    assert not yaml.yaml_key_equal([1], (1,))


def test_shared_node_identity_on_load():
    data = load(SHARED_NODE_DOC)
    shared = data['shared']
    assert data['copy'] is shared
    # the same anchored node used as a key yields the identical object
    assert data.keys()[1] is shared
    assert data[shared] == 'shared-as-key'


def test_roundtrip_preserves_entries_types_and_references():
    data = load(SHARED_NODE_DOC)
    dumped = yaml.safe_dump(data)
    reloaded = yaml.safe_load(dumped, preserve=True)

    assert isinstance(reloaded, yaml.PreservedMapping)
    assert len(reloaded) == len(data)

    original_types = [type(key) for key in data.keys()]
    reloaded_types = [type(key) for key in reloaded.keys()]
    assert reloaded_types == original_types

    shared = reloaded['shared']
    assert type(shared) is list
    assert reloaded['copy'] is shared
    assert reloaded.keys()[1] is shared

    nested = shared[2]
    assert isinstance(nested, yaml.PreservedMapping)
    assert nested[['deep', 'key']] == 'deep-value'


def test_roundtrip_complex_and_duplicate_keys():
    text = """
? [1, 2]
: complex
x: first
x: second
"""
    data = load(text)
    reloaded = yaml.safe_load(yaml.safe_dump(data), preserve=True)
    assert len(reloaded) == len(data)
    assert reloaded.entries == data.entries
    # duplicate x entries survive dumping
    assert sum(1 for key in reloaded.keys() if key == 'x') == 2


def test_dump_does_not_stringify_complex_keys():
    data = load(SEQUENCE_KEY_DOC)
    dumped = yaml.safe_dump(data)
    # keys are emitted as YAML structure, not as Python repr text
    assert "['a', 1]" not in dumped
    assert 'sequence-key' in dumped
    reloaded = yaml.safe_load(dumped, preserve=True)
    assert type(reloaded.keys()[0]) is list


def test_default_safe_load_returns_plain_dict():
    data = yaml.safe_load("a: 1\nb: 2\n")
    assert type(data) is dict

    # explicit preserve=False is identical
    assert yaml.safe_load("a: 1\n", preserve=False) == {'a': 1}

    # the unhashable complex key is still an error for plain dicts
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load("? [1, 2]\n: value\n")
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load("? [1, 2]\n: value\n", preserve=False)


def test_preserving_loader_class_entrypoint():
    data = yaml.load(SHARED_NODE_DOC, Loader=yaml.PreservingSafeLoader)
    assert isinstance(data, yaml.PreservedMapping)
    assert data['copy'] is data['shared']


def test_safe_load_all_preserve():
    documents = list(yaml.safe_load_all("a: 1\n---\n? [1]\n: 2\n",
                                        preserve=True))
    assert isinstance(documents[0], yaml.PreservedMapping)
    assert isinstance(documents[1], yaml.PreservedMapping)
    assert documents[1][[1]] == 2


def test_container_operations():
    data = load(DUPLICATE_KEY_DOC)
    assert len(data.values()) == 7
    assert data.get('missing') is None
    assert data.get('missing', 'default') == 'default'

    data['new'] = 'value'
    assert data['new'] == 'value'
    data[1] = 'updated'
    assert data[1] == 'updated'
    assert len(data) == 8
    del data['new']
    assert 'new' not in data
    with pytest.raises(KeyError):
        del data['missing']
