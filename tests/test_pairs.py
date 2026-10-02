import pytest
import yaml


def test_sequence_key():
    data = yaml.load_pairs("? [1, 2]\n: value\n")
    assert isinstance(data, yaml.Pairs)
    assert len(data) == 1
    key, value = data[0]
    assert key == [1, 2] and type(key) is list
    assert value == 'value'


def test_mapping_key():
    data = yaml.load_pairs("? {a: 1}\n: value\n")
    key, value = data[0]
    assert isinstance(key, yaml.Pairs)
    assert key.items() == [('a', 1)]
    assert value == 'value'


def test_duplicate_scalar_keys_preserved():
    data = yaml.load_pairs("dup: 1\ndup: 2\n")
    assert len(data) == 2
    assert data.keys() == ['dup', 'dup']
    assert data.values() == [1, 2]
    # Lookup returns the first matching entry.
    assert data.get('dup') == 1


def test_typed_key_lookup():
    # 1 and true are equal in Python but have different YAML types.
    data = yaml.load_pairs("1: int\ntrue: bool\n1.0: float\n")
    assert len(data) == 3
    assert data.get(1) == 'int'
    assert data.get(True) == 'bool'
    assert data.get(1.0) == 'float'
    assert 1 in data and True in data and 1.0 in data
    assert '1' not in data
    assert data.get(2) is None
    assert data.get(2, 'fallback') == 'fallback'


def test_keys_are_not_repr_strings():
    data = yaml.load_pairs("? [1, 2]\n: v\n")
    key = data[0][0]
    assert not isinstance(key, str)
    assert key == [1, 2]


def test_shared_nodes():
    doc = "- &k [1, 2]\n- ? *k\n  : shared\n"
    data = yaml.load_pairs(doc)
    seq_key_holder = data[1]
    assert isinstance(seq_key_holder, yaml.Pairs)
    # The alias resolves to the same object, not a copy.
    assert seq_key_holder.keys()[0] is data[0]


def test_merge_key_kept_as_literal_entry():
    doc = "base: &b {x: 1}\nderived:\n  <<: *b\n  y: 2\n"
    data = yaml.load_pairs(doc)
    derived = data.get('derived')
    assert isinstance(derived, yaml.Pairs)
    assert derived.keys() == ['<<', 'y']
    # The merged value is the aliased mapping itself.
    assert derived.get('<<') is data.get('base')


def test_roundtrip_entries_types_and_references():
    doc = """
? &k [1, 2]
: seq key
? {a: 1}
: map key
1: int key
true: bool key
dup: first
dup: second
again: *k
"""
    data = yaml.load_pairs(doc)
    out = yaml.safe_dump(data)
    # The dump is a plain YAML mapping, loadable with the same loader.
    assert '!!python' not in out
    copy = yaml.load_pairs(out)

    # Same number of entries, same types, same values.
    assert len(copy) == len(data) == 7
    assert [type(k) for k in copy.keys()] == [type(k) for k in data.keys()]
    assert [type(v) for v in copy.values()] == [type(v) for v in data.values()]
    assert copy == data

    # Reference relationships survive the round-trip: the aliased key
    # and the aliased value are the same object.
    assert copy.get('again') is copy.keys()[0]
    # Duplicate keys are still distinct entries.
    assert copy.keys().count('dup') == 2


def test_pairs_equality():
    left = yaml.load_pairs("1: a\n[k]: [true]\n")
    right = yaml.load_pairs("1: a\n[k]: [true]\n")
    assert left == right
    assert not left != right
    # Different YAML types for a key means different Pairs,
    # even though 1 == True in Python.
    other = yaml.load_pairs("true: a\n[k]: [true]\n")
    assert left != other
    assert left != [('not', 'pairs')]


def test_load_pairs_all():
    docs = list(yaml.load_pairs_all("a: 1\n---\n? [x]\n: 2\n"))
    assert len(docs) == 2
    assert isinstance(docs[0], yaml.Pairs)
    assert docs[0].items() == [('a', 1)]
    assert docs[1].items() == [(['x'], 2)]


def test_safe_load_unchanged():
    # Plain safe_load still returns dicts.
    data = yaml.safe_load("a: 1\nb: [1, 2]\n")
    assert type(data) is dict
    assert data == {'a': 1, 'b': [1, 2]}
    # And still refuses unhashable keys.
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load("? [1, 2]\n: v\n")


def test_pairs_loader_is_safe():
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.load_pairs("!!python/object/new:os.system ['echo hi']\n")
