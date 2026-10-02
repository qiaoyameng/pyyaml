import datetime
import io
import math

import pytest

import yaml
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.representer import Representer
from yaml.resolver import Resolver


SCALARS = """
- yes
- on
- TRUE
- true
- 010
- 0o10
- 0123
- 1e3
- .5
- 3.
- 0b101
- .inf
- .nan
- null
- ~
- 190:20:30
- 2024-01-01
- 2024-01-01T12:00:00Z
"""

OLD_TYPES = [
    bool, bool, bool, bool,
    int, str, int,
    str, float, float,
    int,
    float, float,
    type(None), type(None),
    int,
    datetime.date, datetime.datetime,
]

CORE_TYPES = [
    str, str, bool, bool,
    int, int, int,
    float, float, float,
    str,
    float, float,
    type(None), type(None),
    str,
    str, str,
]


def scalar_loaders():
    return [yaml.CoreSafeLoader, yaml.CoreFullLoader, yaml.CoreUnsafeLoader]


def core_argument_loaders():
    loaders = [(yaml.SafeLoader, "core"), (yaml.FullLoader, "core"),
               (yaml.UnsafeLoader, "core")]
    if hasattr(yaml, "CSafeLoader"):
        loaders.append((yaml.CSafeLoader, "core"))
    return loaders


def scalar_types(values):
    return [type(value) for value in values]


@pytest.mark.parametrize("Loader", scalar_loaders())
def test_core_subclasses_resolve_scalars(Loader):
    loaded = yaml.load(SCALARS, Loader=Loader)

    assert scalar_types(loaded) == CORE_TYPES
    assert loaded[:4] == ["yes", "on", True, True]
    assert loaded[4:7] == [10, 8, 123]
    assert loaded[7:12] == [1000.0, 0.5, 3.0, "0b101", float("inf")]
    assert math.isnan(loaded[12])
    assert loaded[13:15] == [None, None]
    assert loaded[15:] == [
        "190:20:30",
        "2024-01-01",
        "2024-01-01T12:00:00Z",
    ]


@pytest.mark.parametrize("Loader,schema", core_argument_loaders())
def test_loader_instance_schema_resolves_scalars(Loader, schema):
    loaded = yaml.load(SCALARS, Loader=Loader, schema=schema)

    assert scalar_types(loaded) == CORE_TYPES
    assert scalar_types(yaml.load(SCALARS, Loader=Loader)) == OLD_TYPES


def test_old_schema_remains_default():
    loaded = yaml.load(SCALARS, Loader=yaml.SafeLoader)

    assert scalar_types(loaded) == OLD_TYPES
    assert loaded[:4] == [True, True, True, True]
    assert loaded[4:7] == [8, "0o10", 83]
    assert loaded[15] == 685230


@pytest.mark.parametrize("Loader", [yaml.CoreSafeLoader, yaml.SafeLoader])
def test_explicit_tag_takes_priority(Loader):
    schema = "core" if Loader is yaml.SafeLoader else None
    source = """
string: !!str yes
integer: !!int 010
boolean: !!bool true
date: !!timestamp 2024-01-01
"""
    loaded = yaml.load(source, Loader=Loader, schema=schema)

    assert loaded == {
        "string": "yes",
        "integer": 10,
        "boolean": True,
        "date": datetime.date(2024, 1, 1),
    }
    assert scalar_types(loaded.values()) == [str, int, bool, datetime.date]


@pytest.mark.parametrize("Loader", [yaml.CoreSafeLoader, yaml.SafeLoader])
def test_core_explicit_tags_are_validated(Loader):
    schema = "core" if Loader is yaml.SafeLoader else None

    for source in ["!!bool yes", "!!null nope", "!!timestamp 2024-13-01"]:
        with pytest.raises(ConstructorError):
            yaml.load(source, Loader=Loader, schema=schema)
    with pytest.raises(ConstructorError):
        yaml.load("!!float -.nan", Loader=Loader, schema=schema)


@pytest.mark.parametrize("Loader", [yaml.CoreFullLoader, yaml.FullLoader])
def test_core_python_scalar_tags_use_core_rules(Loader):
    schema = "core" if Loader is yaml.FullLoader else None

    loaded = yaml.load(
        "integer: !!python/int 010\n"
        "floating: !!python/float 1e3\n"
        "boolean: !!python/bool true\n",
        Loader=Loader,
        schema=schema,
    )

    assert loaded == {"integer": 10, "floating": 1000.0, "boolean": True}
    assert scalar_types(loaded.values()) == [int, float, bool]

    with pytest.raises(ConstructorError):
        yaml.load("!!python/bool yes", Loader=Loader, schema=schema)


@pytest.mark.parametrize("Dumper", [yaml.CoreSafeDumper, yaml.CoreDumper])
def test_core_dumper_quotes_ambiguous_strings(Dumper):
    values = ["yes", "010", "1e3", "null", "2024-01-01"]

    output = yaml.dump(values, Dumper=Dumper)
    reloaded = yaml.load(output, Loader=yaml.CoreSafeLoader)

    assert output == (
        "- yes\n"
        "- '010'\n"
        "- '1e3'\n"
        "- 'null'\n"
        "- 2024-01-01\n"
    )
    assert reloaded == values
    assert scalar_types(reloaded) == [str, str, str, str, str]


@pytest.mark.parametrize("Dumper", [yaml.SafeDumper]
        + ([yaml.CSafeDumper] if hasattr(yaml, "CSafeDumper") else []))
def test_dumper_instance_schema_quotes_ambiguous_strings(Dumper):
    output = yaml.dump(["yes", "010"], Dumper=Dumper, schema="core")

    assert output == "- yes\n- '010'\n"
    assert yaml.load(output, Loader=yaml.SafeLoader, schema="core") == ["yes", "010"]
    assert yaml.dump(["yes", "010"], Dumper=Dumper) == "- 'yes'\n- '010'\n"


def test_loader_schema_is_isolated_to_instance():
    old = yaml.SafeLoader(SCALARS)
    core = yaml.SafeLoader(SCALARS, schema="core")

    try:
        old_data = old.get_single_data()
        core_data = core.get_single_data()
    finally:
        old.dispose()
        core.dispose()

    assert type(old_data[0]) is bool
    assert type(core_data[0]) is str
    assert type(yaml.load("yes", Loader=yaml.SafeLoader)) is bool

    assert yaml.SafeLoader.yaml_implicit_resolvers \
        is Resolver.yaml_implicit_resolvers
    assert yaml.SafeLoader.yaml_constructors is SafeConstructor.yaml_constructors
    assert yaml.Dumper.yaml_implicit_resolvers \
        is Resolver.yaml_implicit_resolvers
    assert yaml.Dumper.yaml_representers \
        is Representer.yaml_representers


def test_interleaved_old_and_core_loaders_do_not_interfere():
    old_values = []
    core_values = []
    for _ in range(3):
        old_values.append(yaml.safe_load("[yes, on, 010, 0b101, 1e3]"))
        core_values.append(
            yaml.safe_load("[yes, on, 010, 0b101, 1e3]", schema="core"))

    for old, core in zip(old_values, core_values):
        assert scalar_types(old) == [bool, bool, int, int, str]
        assert old == [True, True, 8, 5, "1e3"]
        assert scalar_types(core) == [str, str, int, str, float]
        assert core == ["yes", "on", 10, "0b101", 1000.0]

        old_output = yaml.safe_dump(core)
        core_output = yaml.safe_dump(old, schema="core")

        assert yaml.safe_load(old_output) == core
        assert yaml.safe_load(core_output, schema="core") == old
        assert scalar_types(yaml.safe_load(old_output)) == [
            str, str, int, str, float]
        assert scalar_types(yaml.safe_load(core_output, schema="core")) == [
            bool, bool, int, int, str]

        core_output_of_core = yaml.safe_dump(core, schema="core")
        old_output_of_old = yaml.safe_dump(old)
        assert yaml.safe_load(core_output_of_core, schema="core") == core
        assert yaml.safe_load(old_output_of_old) == old


def test_dumper_schema_is_isolated_to_instance():
    old_stream = io.StringIO()
    core_stream = io.StringIO()
    old_dumper = yaml.SafeDumper(old_stream)
    core_dumper = yaml.SafeDumper(core_stream, schema="core")

    for dumper in (old_dumper, core_dumper):
        dumper.open()
        dumper.represent("yes")
        dumper.close()
        dumper.dispose()

    assert old_stream.getvalue() == "'yes'\n"
    assert core_stream.getvalue() == "yes\n...\n"
    assert yaml.safe_load(old_stream.getvalue()) == "yes"
    assert yaml.safe_load(core_stream.getvalue(), schema="core") == "yes"


def test_invalid_schema_is_rejected():
    with pytest.raises(ValueError):
        yaml.SafeLoader("yes", schema="json")
    with pytest.raises(ValueError):
        yaml.SafeDumper(io.StringIO(), schema="json")
    with pytest.raises(ValueError):
        yaml.CoreSafeLoader("yes", schema="json")
    with pytest.raises(ValueError):
        yaml.CoreSafeDumper(io.StringIO(), schema="json")


@pytest.mark.parametrize("Dumper", [yaml.CoreSafeDumper, yaml.SafeDumper])
def test_core_dump_load_roundtrip_preserves_key_values_and_types(Dumper):
    schema = "core" if Dumper is yaml.SafeDumper else None
    loaded = yaml.load(
        "yes: string\n1: integer\n",
        Loader=yaml.CoreSafeLoader,
    )
    output = yaml.dump(loaded, Dumper=Dumper, schema=schema)
    reloaded = yaml.load(output, Loader=yaml.CoreSafeLoader)

    assert list(loaded) == ["yes", 1]
    assert loaded == {"yes": "string", 1: "integer"}
    assert reloaded == loaded
    assert list(reloaded) == list(loaded)
    assert type(reloaded["yes"]) is str
    assert type(list(reloaded)[1]) is int
    assert output.splitlines() == ["yes: string", "1: integer"]


def test_core_still_merges_true_and_integer_keys():
    loaded = yaml.load("1: integer\ntrue: boolean\n", Loader=yaml.CoreSafeLoader)

    assert list(loaded) == [1]
    assert loaded == {True: "boolean"}


def test_old_schema_merges_bool_and_integer_keys():
    loaded = yaml.load("yes: string\n1: integer\n", Loader=yaml.SafeLoader)

    assert list(loaded) == [True]
    assert loaded == {True: "integer"}


def test_core_timestamp_roundtrips_with_explicit_tag():
    value = datetime.datetime(2024, 1, 1, 12, tzinfo=datetime.timezone.utc)

    output = yaml.safe_dump(value, schema="core")
    reloaded = yaml.safe_load(output, schema="core")

    assert output.startswith("!!timestamp ")
    assert reloaded == value
    assert type(reloaded) is datetime.datetime


@pytest.mark.parametrize("Dumper,schema", [
    (yaml.CoreSafeDumper, None),
    (yaml.SafeDumper, "core"),
])
def test_core_roundtrip_keeps_timestamp_values_and_strings_apart(Dumper, schema):
    value = {
        "timestamp": datetime.date(2024, 1, 1),
        "string": "2024-01-01",
        "boolean": True,
        "boolean_string": "yes",
    }

    output = yaml.dump(value, Dumper=Dumper, schema=schema, sort_keys=False)
    reloaded = yaml.load(output, Loader=yaml.CoreSafeLoader)

    assert reloaded == value
    assert scalar_types(reloaded.values()) == [
        datetime.date, str, bool, str]
    assert "!!timestamp" in output
