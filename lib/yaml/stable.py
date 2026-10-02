"""
Deterministic ("stable") YAML output for configuration fingerprints.

`stable_dump` serializes a restricted set of Python values to YAML bytes
that depend only on the logical content to be represented, never on dict
insertion order, object addresses, or process state.  Dumping the same
content twice -- in the same process or in different processes -- always
produces the same byte string.

Supported values (checked before serialization, anything else is rejected
with `StableDumpError`):

    None, bool, int, float, str, list, tuple, dict

Mapping keys must be `str` instances exactly.  Types are matched
exactly, so subclasses of the supported types are rejected as well.

Stability rules:

- mapping keys are emitted sorted by Unicode code point;
- the encoding is always UTF-8 and line breaks are always "\\n";
- indentation, width, flow style and document markers are fixed;
- floats use Python's shortest round-trip representation, with the
  special values ``.nan``, ``.inf`` and ``-.inf``;
- shared containers (including recursive references) are emitted once
  with anchors named ``id001``, ``id002``, ... assigned in document
  traversal order, so aliases never depend on object addresses.

Examples
--------
>>> import yaml
>>> yaml.stable_dump({'b': 1, 'a': [True, None]})
b'a:\\n- true\\n- null\\nb: 1\\n'
>>> yaml.stable_dump({'a': 1, 2: 'x'})
Traceback (most recent call last):
...
yaml.stable.StableDumpError: stable_dump only accepts string mapping keys, got key of type int
"""

__all__ = ['StableDumpError', 'StableDumper', 'stable_dump']

import io

from .error import YAMLError
from .emitter import Emitter
from .serializer import Serializer
from .representer import SafeRepresenter
from .resolver import Resolver


class StableDumpError(YAMLError):
    """Raised when data cannot be serialized by stable_dump."""


_SCALAR_TYPES = (type(None), bool, int, float, str)


def _validate(data):
    """Check that *data* only contains values stable_dump supports.

    Walks the object graph iteratively so recursive structures and deep
    nesting are handled safely.  Error messages only mention type names;
    ``repr`` is never called on the offending objects.
    """
    seen = set()
    stack = [data]
    while stack:
        value = stack.pop()
        value_type = type(value)
        if value_type in _SCALAR_TYPES:
            continue
        if value_type is list or value_type is tuple:
            if id(value) in seen:
                continue
            seen.add(id(value))
            stack.extend(value)
        elif value_type is dict:
            if id(value) in seen:
                continue
            seen.add(id(value))
            for key, item in value.items():
                if type(key) is not str:
                    raise StableDumpError(
                            "stable_dump only accepts string mapping keys, "
                            "got key of type %s" % type(key).__name__)
                stack.append(item)
        else:
            raise StableDumpError(
                    "stable_dump does not support objects of type %s"
                    % value_type.__name__)


class StableRepresenter(SafeRepresenter):

    def represent_dict(self, data):
        # Keys are validated to be strings; sort by Unicode code point so
        # the output does not depend on insertion order.
        value = sorted(data.items(), key=lambda item: item[0])
        return self.represent_mapping(
                'tag:yaml.org,2002:map', value)


StableRepresenter.add_representer(dict,
        StableRepresenter.represent_dict)


class StableDumper(Emitter, Serializer, StableRepresenter, Resolver):
    """A SafeDumper with every formatting option pinned to a fixed value."""

    def __init__(self, stream):
        Emitter.__init__(self, stream, canonical=False,
                indent=2, width=80,
                allow_unicode=True, line_break='\n')
        Serializer.__init__(self, encoding='utf-8',
                explicit_start=False, explicit_end=False,
                version=None, tags=None)
        StableRepresenter.__init__(self, default_style=None,
                default_flow_style=False, sort_keys=False)
        Resolver.__init__(self)


def stable_dump(data, stream=None):
    """
    Serialize a Python object into deterministic YAML bytes.

    Only None, bool, int, float, str, list, tuple and dict values with
    string keys are accepted; anything else raises StableDumpError.
    If stream is None, return the produced bytes (always UTF-8).
    """
    _validate(data)
    getvalue = None
    if stream is None:
        stream = io.BytesIO()
        getvalue = stream.getvalue
    dumper = StableDumper(stream)
    try:
        dumper.open()
        dumper.represent(data)
        dumper.close()
    finally:
        dumper.dispose()
    if getvalue:
        return getvalue()
