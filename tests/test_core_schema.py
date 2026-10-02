import datetime

import pytest

import yaml
from yaml.constructor import ConstructorError
from yaml.resolver import CoreResolver, Resolver


# (source, yaml 1.1 value, yaml 1.2 core value)
AMBIGUOUS_SCALARS = [
    ("yes", True, "yes"),
    ("No", False, "No"),
    ("on", True, "on"),
    ("OFF", False, "OFF"),
    ("true", True, True),
    ("False", False, False),
    ("010", 8, 10),
    ("0o17", "0o17", 15),
    ("0b101", 5, "0b101"),
    ("0x1F", 31, 31),
    ("1:20", 80, "1:20"),
    ("1e5", "1e5", 100000.0),
    ("1.5", 1.5, 1.5),
    ("+.5", "+.5", 0.5),
    ("-2", -2, -2),
    ("null", None, None),
    ("~", None, None),
    (".inf", float("inf"), float("inf")),
    ("2024-01-02", datetime.date(2024, 1, 2), datetime.date(2024, 1, 2)),
    (
        "2001-12-15 02:59:43",
        datetime.datetime(2001, 12, 15, 2, 59, 43),
        datetime.datetime(2001, 12, 15, 2, 59, 43),
    ),
]


@pytest.mark.parametrize("source,yaml11,core", AMBIGUOUS_SCALARS)
def test_scalar_resolution_per_mode(source, yaml11, core):
    assert yaml.load(source, Loader=yaml.SafeLoader) == yaml11
    assert yaml.load(source, Loader=yaml.CoreLoader) == core
    assert type(yaml.load(source, Loader=yaml.SafeLoader)) is type(yaml11)
    assert type(yaml.load(source, Loader=yaml.CoreLoader)) is type(core)


def test_interleaved_modes_do_not_interfere():
    # Alternating loaders must not leak resolution rules into each other.
    for _ in range(3):
        for source, yaml11, core in AMBIGUOUS_SCALARS:
            assert yaml.load(source, Loader=yaml.SafeLoader) == yaml11
            assert yaml.load(source, Loader=yaml.CoreLoader) == core
            assert yaml.load(source, Loader=yaml.SafeLoader) == yaml11


def test_interleaved_dumpers_do_not_interfere():
    for _ in range(3):
        assert yaml.load(yaml.dump("yes", Dumper=yaml.SafeDumper),
                Loader=yaml.SafeLoader) == "yes"
        assert yaml.load(yaml.dump("yes", Dumper=yaml.CoreDumper),
                Loader=yaml.CoreLoader) == "yes"
        assert yaml.load(yaml.dump("true", Dumper=yaml.CoreDumper),
                Loader=yaml.CoreLoader) == "true"
        # The YAML 1.1 dumper is unaffected by core dumper usage.
        assert yaml.dump("yes", Dumper=yaml.SafeDumper).strip() == "'yes'"


def test_resolver_tables_are_not_shared():
    assert CoreResolver.yaml_implicit_resolvers is not Resolver.yaml_implicit_resolvers
    for first, resolvers in Resolver.yaml_implicit_resolvers.items():
        assert CoreResolver.yaml_implicit_resolvers.get(first) is not resolvers
    # Using the core mode leaves the global YAML 1.1 tables untouched.
    yaml.load("on", Loader=yaml.CoreLoader)
    yaml.core_dump("on")
    assert yaml.load("on", Loader=yaml.SafeLoader) is True
    assert yaml.load("010", Loader=yaml.SafeLoader) == 8


def test_explicit_tag_takes_priority_over_resolution():
    # An explicit tag forces the constructor regardless of the schema.
    for loader in (yaml.SafeLoader, yaml.CoreLoader):
        assert yaml.load("!!str yes", Loader=loader) == "yes"
        assert yaml.load("!!str 010", Loader=loader) == "010"
        assert yaml.load("!!str true", Loader=loader) == "true"
    # Construction of an explicitly tagged scalar follows the mode's rules.
    assert yaml.load("!!bool yes", Loader=yaml.SafeLoader) is True
    assert yaml.load("!!int 010", Loader=yaml.SafeLoader) == 8
    assert yaml.load("!!bool true", Loader=yaml.CoreLoader) is True
    assert yaml.load("!!int 010", Loader=yaml.CoreLoader) == 10
    assert yaml.load("!!int 0o17", Loader=yaml.CoreLoader) == 15
    with pytest.raises(ConstructorError):
        yaml.load("!!bool yes", Loader=yaml.CoreLoader)


def test_core_dump_quotes_core_typed_strings():
    # Strings that the core schema would resolve as non-str must be quoted.
    assert yaml.dump("010", Dumper=yaml.CoreDumper).strip() == "'010'"
    assert yaml.dump("0o17", Dumper=yaml.CoreDumper).strip() == "'0o17'"
    assert yaml.dump("1e5", Dumper=yaml.CoreDumper).strip() == "'1e5'"
    assert yaml.dump("true", Dumper=yaml.CoreDumper).strip() == "'true'"
    assert yaml.dump("null", Dumper=yaml.CoreDumper).strip() == "'null'"
    # Strings that are plain scalars in the core schema stay unquoted.
    assert yaml.dump("yes", Dumper=yaml.CoreDumper).splitlines()[0] == "yes"
    assert yaml.dump("on", Dumper=yaml.CoreDumper).splitlines()[0] == "on"
    assert yaml.dump("0b101", Dumper=yaml.CoreDumper).splitlines()[0] == "0b101"
    # The YAML 1.1 dumper quotes its own ambiguous set instead
    # (``0b101`` is an integer in YAML 1.1 but a string in the core schema).
    assert yaml.dump("on", Dumper=yaml.SafeDumper).strip() == "'on'"
    assert yaml.dump("0b101", Dumper=yaml.SafeDumper).strip() == "'0b101'"


def assert_same_typed_value(expected, actual):
    assert type(expected) is type(actual)
    if isinstance(expected, dict):
        assert len(expected) == len(actual)
        unmatched = list(actual.items())
        for key, value in expected.items():
            for candidate in unmatched:
                if type(candidate[0]) is type(key) and candidate[0] == key:
                    unmatched.remove(candidate)
                    assert_same_typed_value(value, candidate[1])
                    break
            else:
                raise AssertionError("key %r not found in %r" % (key, actual))
    elif isinstance(expected, (list, tuple)):
        assert len(expected) == len(actual)
        for expected_item, actual_item in zip(expected, actual):
            assert_same_typed_value(expected_item, actual_item)
    elif isinstance(expected, float) and expected != expected:
        assert actual != actual
    else:
        assert expected == actual


def roundtrip_data():
    return {
        "yes": "no",
        "on": "off",
        "bool_word": "true",
        "null_word": "null",
        "tilde": "~",
        "leading_zero": "010",
        "octal_like": "0o17",
        "binary_like": "0b101",
        "sexagesimal_like": "1:20",
        "exponent_like": "1e5",
        "hex_like": "0x1F",
        "int": 10,
        "neg_int": -7,
        "float": 2.5,
        "bool": True,
        "false": False,
        "none": None,
        "date": datetime.date(2024, 1, 2),
        "timestamp": datetime.datetime(2024, 1, 2, 3, 4, 5),
        "nested": {"list": ["yes", 1, 1.5, None, True, "0o17"]},
    }


def test_core_dump_load_roundtrip():
    data = roundtrip_data()
    assert_same_typed_value(data, yaml.load(
        yaml.dump(data, Dumper=yaml.CoreDumper), Loader=yaml.CoreLoader))


def test_yaml11_dump_load_roundtrip():
    data = roundtrip_data()
    assert_same_typed_value(data, yaml.load(
        yaml.dump(data, Dumper=yaml.SafeDumper), Loader=yaml.SafeLoader))


def test_core_convenience_functions_roundtrip():
    data = roundtrip_data()
    assert_same_typed_value(data, yaml.core_load(yaml.core_dump(data)))
    assert_same_typed_value([data, data],
            list(yaml.core_load_all(yaml.core_dump_all([data, data]))))


def test_yaml11_merges_boolean_like_mapping_keys():
    # yes/true/on all construct to True, collapsing into a single key.
    data = yaml.load("{yes: a, true: b, on: c}", Loader=yaml.SafeLoader)
    assert data == {True: "c"}
    assert len(data) == 1


def test_core_keeps_boolean_like_mapping_keys_distinct():
    data = yaml.load("{yes: a, true: b, on: c}", Loader=yaml.CoreLoader)
    assert data == {"yes": "a", True: "b", "on": "c"}
    assert len(data) == 3


def test_yaml11_merges_int_and_boolean_mapping_keys():
    # 1 == True in Python, so the YAML 1.1 boolean keys collide with 1.
    data = yaml.load("{1: a, true: b, yes: c}", Loader=yaml.SafeLoader)
    assert len(data) == 1
    assert data == {1: "c"}


def test_core_still_merges_int_and_boolean_mapping_keys():
    # The core schema keeps 1 and true distinct as YAML types, but the
    # constructed Python dict still merges them because 1 == True.
    data = yaml.load("{1: a, true: b}", Loader=yaml.CoreLoader)
    assert len(data) == 1
    assert data == {1: "b"}


def test_leading_zero_keys_merge_only_in_core_mode():
    # YAML 1.1: 010 is octal 8, distinct from decimal 10.
    data = yaml.load("{010: a, 10: b}", Loader=yaml.SafeLoader)
    assert data == {8: "a", 10: "b"}
    # Core schema: 010 is decimal 10 and collides with 10.
    data = yaml.load("{010: a, 10: b}", Loader=yaml.CoreLoader)
    assert data == {10: "b"}
    assert len(data) == 1
