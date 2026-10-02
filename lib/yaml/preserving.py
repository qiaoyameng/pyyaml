__all__ = ['PreservedMapping', 'yaml_key_equal',
        'PreservingSafeConstructor', 'PreservingSafeLoader',
        'PreservingSafeRepresenter', 'PreservingSafeDumper']

from .constructor import SafeConstructor, ConstructorError
from .nodes import *
from .reader import *
from .scanner import *
from .parser import *
from .composer import *
from .resolver import *
from .representer import SafeRepresenter, Representer
from .emitter import *
from .serializer import *


def yaml_key_equal(left, right):
    """Equality rule used when looking up entries in a :class:`PreservedMapping`.

    It follows YAML's type system rather than Python's: scalars only match
    values of the exact same Python type, so the integer ``1`` and the boolean
    ``True`` (which are equal in Python, but carry distinct YAML tags) are
    different keys.  Containers are compared structurally and recurse with the
    same rule.
    """
    if isinstance(left, PreservedMapping) or isinstance(right, PreservedMapping):
        left_entries = _mapping_entries(left)
        right_entries = _mapping_entries(right)
        if left_entries is None or right_entries is None:
            return False
        if len(left_entries) != len(right_entries):
            return False
        for (left_key, left_value), (right_key, right_value) in zip(
                left_entries, right_entries):
            if not yaml_key_equal(left_key, right_key):
                return False
            if not yaml_key_equal(left_value, right_value):
                return False
        return True
    if isinstance(left, (list, tuple)):
        if type(left) is not type(right):
            return False
        if len(left) != len(right):
            return False
        return all(yaml_key_equal(item, other)
                   for item, other in zip(left, right))
    if isinstance(left, dict) or isinstance(right, dict):
        return False
    if type(left) is not type(right):
        return False
    return left == right


def _mapping_entries(value):
    if isinstance(value, PreservedMapping):
        return value._entries
    if isinstance(value, dict):
        try:
            return list(value.items())
        except TypeError:
            return None
    return None


class PreservedMapping:
    """A YAML mapping loaded as an ordered list of ``(key, value)`` entries.

    Unlike a regular :class:`dict`, this container:

    * keeps entries in document order;
    * keeps entries with duplicate keys;
    * accepts complex keys that are not hashable (such as sequences or nested
      mappings);
    * resolves lookups with YAML type semantics (see :func:`yaml_key_equal`),
      so ``1`` and ``true`` remain distinct keys.

    The entries are available through :attr:`entries` (a fresh list of
    ``(key, value)`` tuples) or :meth:`items`/:meth:`keys`/:meth:`values`.
    """

    __slots__ = ('_entries',)

    def __init__(self, entries=()):
        self._entries = [(key, value) for key, value in entries]

    @property
    def entries(self):
        return list(self._entries)

    def __iter__(self):
        for key, value in self._entries:
            yield key

    def __reversed__(self):
        for key, value in reversed(self._entries):
            yield key

    def __len__(self):
        return len(self._entries)

    def __bool__(self):
        return bool(self._entries)

    def _index(self, key):
        for index in range(len(self._entries) - 1, -1, -1):
            if yaml_key_equal(self._entries[index][0], key):
                return index
        return None

    def __contains__(self, key):
        return self._index(key) is not None

    def __getitem__(self, key):
        index = self._index(key)
        if index is None:
            raise KeyError(key)
        return self._entries[index][1]

    def __setitem__(self, key, value):
        index = self._index(key)
        if index is None:
            self._entries.append((key, value))
        else:
            self._entries[index] = (key, value)

    def __delitem__(self, key):
        index = self._index(key)
        if index is None:
            raise KeyError(key)
        del self._entries[index]

    def get(self, key, default=None):
        index = self._index(key)
        if index is None:
            return default
        return self._entries[index][1]

    def keys(self):
        return [key for key, value in self._entries]

    def values(self):
        return [value for key, value in self._entries]

    def items(self):
        return list(self._entries)

    def __eq__(self, other):
        if isinstance(other, PreservedMapping):
            other_entries = other._entries
        elif isinstance(other, (list, tuple)):
            other_entries = other
        else:
            return NotImplemented
        if len(self._entries) != len(other_entries):
            return False
        for (key, value), (other_key, other_value) in zip(
                self._entries, other_entries):
            if not yaml_key_equal(key, other_key):
                return False
            if value != other_value:
                return False
        return True

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    __hash__ = None

    def __repr__(self):
        return 'PreservedMapping(%r)' % (self._entries,)


class PreservingSafeConstructor(SafeConstructor):

    def construct_mapping(self, node, deep=False):
        if isinstance(node, MappingNode):
            self.flatten_mapping(node)
        if not isinstance(node, MappingNode):
            raise ConstructorError(None, None,
                    "expected a mapping node, but found %s" % node.id,
                    node.start_mark)
        mapping = PreservedMapping()
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            value = self.construct_object(value_node, deep=deep)
            mapping._entries.append((key, value))
        return mapping

    def construct_yaml_map(self, node):
        data = PreservedMapping()
        yield data
        value = self.construct_mapping(node)
        data._entries.extend(value._entries)


PreservingSafeConstructor.add_constructor(
        'tag:yaml.org,2002:map',
        PreservingSafeConstructor.construct_yaml_map)


class PreservingSafeLoader(Reader, Scanner, Parser, Composer,
        PreservingSafeConstructor, Resolver):

    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        PreservingSafeConstructor.__init__(self)
        Resolver.__init__(self)


class PreservingSafeRepresenter(SafeRepresenter):

    def represent_preserved_mapping(self, data):
        # The entries are emitted in their stored order on purpose, ignoring
        # `sort_keys`, so that duplicates and complex keys round-trip.
        value = []
        node = MappingNode('tag:yaml.org,2002:map', value)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node
        best_style = True
        for item_key, item_value in data._entries:
            node_key = self.represent_data(item_key)
            node_value = self.represent_data(item_value)
            if not (isinstance(node_key, ScalarNode) and not node_key.style):
                best_style = False
            if not (isinstance(node_value, ScalarNode) and not node_value.style):
                best_style = False
            value.append((node_key, node_value))
        if self.default_flow_style is not None:
            node.flow_style = self.default_flow_style
        else:
            node.flow_style = best_style
        return node


SafeRepresenter.add_representer(PreservedMapping,
        PreservingSafeRepresenter.represent_preserved_mapping)
Representer.add_representer(PreservedMapping,
        PreservingSafeRepresenter.represent_preserved_mapping)


class PreservingSafeDumper(Emitter, Serializer, PreservingSafeRepresenter,
        Resolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        PreservingSafeRepresenter.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)
