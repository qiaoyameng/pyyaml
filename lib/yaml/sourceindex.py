"""
Source-indexed safe loading.

This module provides a safe loading entry point that, in addition to the
plain Python data produced by ``yaml.safe_load``, returns a separate
``SourceIndex`` describing where every value in the loaded document was
written in the original YAML stream.  The index maps *paths* (tuples of
``Key``/``Index`` segments) to ``SourceEntry`` records carrying line/column
locations, so a validation layer that only holds the Python dict can still
point the user at the exact line a bad value came from.

Semantics:

* Mapping keys, mapping values and sequence items are all indexed.  Path
  segments distinguish string keys (``Key``) from numeric sequence indices
  (``Index``), so ``{0: x}`` and ``[x]`` never collide.
* Merge keys (``<<``) and aliases (``*a``) record both the definition
  location and the use location of every affected field.
* Shared objects (anchors reused in several places) are indexed once, at
  their definition site; every other occurrence is a lightweight
  ``reference`` entry pointing at the canonical path, so shared subtrees
  are never duplicated in the index.
* Recursive aliases (``&a [*a]``) are expressed as a reference back to an
  ancestor path -- a finite relation, never an infinite path expansion.
* Multi-document streams record the document number on every entry.
"""

__all__ = [
    'Key',
    'Index',
    'SourceLocation',
    'SourceEntry',
    'SourceIndex',
    'IndexedSafeLoader',
    'safe_load_with_index',
    'safe_load_all_with_index',
    'format_path',
]

from .composer import Composer, ComposerError
from .constructor import SafeConstructor
from .events import AliasEvent
from .loader import SafeLoader
from .nodes import MappingNode, SequenceNode


class Key:
    """Path segment addressing a mapping value by its (arbitrary-typed) key."""
    __slots__ = ('value',)
    kind = 'key'

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return type(other) is Key and self.value == other.value

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((Key, self.value))

    def __repr__(self):
        return 'Key(%r)' % (self.value,)


class Index:
    """Path segment addressing a sequence item by its numeric position."""
    __slots__ = ('value',)
    kind = 'index'

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return type(other) is Index and self.value == other.value

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash((Index, self.value))

    def __repr__(self):
        return 'Index(%r)' % (self.value,)


def format_path(path):
    """Render a path tuple as a JSONPath-like string, e.g. ``$.a.b[0]``."""
    parts = ['$']
    for segment in path:
        if isinstance(segment, Index):
            parts.append('[%d]' % (segment.value,))
        elif isinstance(segment.value, str) and segment.value.isidentifier():
            parts.append('.%s' % (segment.value,))
        else:
            parts.append('[%r]' % (segment.value,))
    return ''.join(parts)


class SourceLocation:
    """A 1-based line/column position in the YAML stream."""
    __slots__ = ('document', 'line', 'column', 'end_line', 'end_column', 'name')

    def __init__(self, document, line, column,
            end_line=None, end_column=None, name=None):
        self.document = document
        self.line = line
        self.column = column
        self.end_line = end_line
        self.end_column = end_column
        self.name = name

    @classmethod
    def from_mark(cls, mark, document, end_mark=None):
        if mark is None:
            return None
        return cls(
            document=document,
            line=mark.line + 1,
            column=mark.column + 1,
            end_line=(end_mark.line + 1) if end_mark is not None else None,
            end_column=(end_mark.column + 1) if end_mark is not None else None,
            name=mark.name,
        )

    def __repr__(self):
        return 'SourceLocation(doc=%d, line=%d, column=%d)' % (
                self.document, self.line, self.column)


class SourceEntry:
    """Index record for one path of the loaded document.

    ``kind`` is ``'value'`` for the place where a node is defined and
    ``'reference'`` for additional occurrences of a shared node (alias
    uses, merged collections, recursive aliases).  ``via`` is ``None`` for
    ordinary fields, ``'merge'`` for fields that arrived through a ``<<``
    merge key and ``'alias'`` for occurrences written as ``*anchor``.
    ``target`` is the canonical (definition) path for references.
    """
    __slots__ = ('path', 'document', 'kind', 'defined_at', 'key_at',
            'used_at', 'via', 'anchor', 'target')

    def __init__(self, path, document, kind, defined_at, key_at=None,
            used_at=None, via=None, anchor=None, target=None):
        self.path = path
        self.document = document
        self.kind = kind
        self.defined_at = defined_at
        self.key_at = key_at
        self.used_at = used_at
        self.via = via
        self.anchor = anchor
        self.target = target

    def __repr__(self):
        return 'SourceEntry(%s, kind=%r, via=%r, defined_at=%r)' % (
                format_path(self.path), self.kind, self.via, self.defined_at)


class SourceIndex:
    """Position metadata for one loaded YAML document."""

    def __init__(self, document=0):
        self.document = document
        self.entries = {}

    def add(self, entry):
        self.entries[entry.path] = entry

    @staticmethod
    def path(*segments):
        """Build a path tuple, mapping ``str`` to ``Key`` and ``int`` to
        ``Index``.  Pass ``Key``/``Index`` segments explicitly when a
        mapping has integer keys."""
        return tuple(
                segment if isinstance(segment, (Key, Index))
                else Key(segment) if isinstance(segment, str)
                else Index(segment) if isinstance(segment, int)
                else Key(segment)
                for segment in segments)

    def lookup(self, *segments):
        return self.entries[self.path(*segments)]

    def __getitem__(self, path):
        return self.entries[path]

    def __contains__(self, path):
        return path in self.entries

    def __iter__(self):
        return iter(self.entries.values())

    def __len__(self):
        return len(self.entries)

    @staticmethod
    def format(path):
        return format_path(path)


class IndexedComposer(Composer):
    """Composer that additionally records alias use sites and anchor names."""

    def __init__(self):
        Composer.__init__(self)
        self.document_index = -1
        self.alias_uses = {}
        self.anchor_names = {}

    def compose_document(self):
        self.document_index += 1
        self.alias_uses = {}
        self.anchor_names = {}
        return super().compose_document()

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            event = self.get_event()
            anchor = event.anchor
            if anchor not in self.anchors:
                raise ComposerError(None, None, "found undefined alias %r"
                        % anchor, event.start_mark)
            node = self.anchors[anchor]
            self.alias_uses.setdefault(id(node), []).append(
                    (event.start_mark, self.document_index))
            return node
        return super().compose_node(parent, index)

    def _register_anchor(self, anchor, node):
        if anchor is not None:
            self.anchor_names[id(node)] = anchor

    def compose_scalar_node(self, anchor):
        node = super().compose_scalar_node(anchor)
        self._register_anchor(anchor, node)
        return node

    def compose_sequence_node(self, anchor):
        node = super().compose_sequence_node(anchor)
        self._register_anchor(anchor, node)
        return node

    def compose_mapping_node(self, anchor):
        node = super().compose_mapping_node(anchor)
        self._register_anchor(anchor, node)
        return node


class IndexedConstructor(SafeConstructor):
    """SafeConstructor that records where merge keys brought fields in."""

    def __init__(self):
        SafeConstructor.__init__(self)
        self.merge_marks = {}
        self._merge_records = {}
        self.last_source_index = None

    def flatten_mapping(self, node):
        if id(node) not in self._merge_records:
            self._merge_records[id(node)] = [
                    (key_node.start_mark, value_node)
                    for key_node, value_node in node.value
                    if key_node.tag == 'tag:yaml.org,2002:merge']
        super().flatten_mapping(node)
        records = self._merge_records[id(node)]
        if records and id(node) not in self.merge_marks:
            origins = {}
            seen = set()
            for key_mark, value_node in records:
                # A merge written as ``<<: *anchor`` consumed an alias event;
                # discard it here so remaining alias uses stay in order, and
                # prefer the alias position as the use site.
                uses = self.alias_uses.get(id(value_node))
                if uses:
                    uses.pop(0)
                if isinstance(value_node, MappingNode):
                    sources = [value_node]
                elif isinstance(value_node, SequenceNode):
                    sources = [subnode for subnode in value_node.value
                            if isinstance(subnode, MappingNode)]
                else:
                    sources = []
                for source in sources:
                    for pair in source.value:
                        key_id = id(pair[0].value)
                        if key_id not in seen:
                            seen.add(key_id)
                            origins[id(pair[0])] = key_mark
            self.merge_marks[id(node)] = origins

    def construct_document(self, node):
        self.merge_marks = {}
        self._merge_records = {}
        data = super().construct_document(node)
        index = SourceIndex(document=self.document_index)
        _build_source_index(self, node, data, index)
        self.last_source_index = index
        return data


class IndexedSafeLoader(IndexedComposer, IndexedConstructor, SafeLoader):
    """SafeLoader that also produces a SourceIndex per document."""

    def __init__(self, stream):
        SafeLoader.__init__(self, stream)
        IndexedComposer.__init__(self)
        IndexedConstructor.__init__(self)

    def get_data_with_index(self):
        """Return ``(data, SourceIndex)`` for the next document."""
        if self.check_data():
            data = self.get_data()
            return data, self.last_source_index

    def get_single_data_with_index(self):
        """Return ``(data, SourceIndex)`` for a single-document stream."""
        node = self.get_single_node()
        if node is None:
            return None, SourceIndex(document=0)
        data = self.construct_document(node)
        return data, self.last_source_index


def _build_source_index(loader, root_node, root_data, index):
    visited = {}
    key_constructor = SafeConstructor()
    document = loader.document_index

    def location(mark):
        return SourceLocation.from_mark(mark, document)

    def pop_alias_use(node):
        uses = loader.alias_uses.get(id(node))
        if uses:
            return uses.pop(0)[0]
        return None

    def walk(node, data, path, via=None, used_at=None, key_at=None):
        anchor = loader.anchor_names.get(id(node))
        if id(node) in visited:
            alias_mark = pop_alias_use(node)
            index.add(SourceEntry(
                path=path, document=document, kind='reference',
                defined_at=location(node.start_mark),
                key_at=key_at,
                used_at=location(alias_mark) if alias_mark is not None else used_at,
                via='alias' if alias_mark is not None else via,
                anchor=anchor,
                target=visited[id(node)]))
            return
        visited[id(node)] = path
        index.add(SourceEntry(
            path=path, document=document, kind='value',
            defined_at=location(node.start_mark),
            key_at=key_at, used_at=used_at, via=via, anchor=anchor))
        if isinstance(node, MappingNode):
            merge_origins = loader.merge_marks.get(id(node), {})
            for key_node, value_node in node.value:
                key = key_constructor.construct_object(key_node, deep=True)
                merge_mark = merge_origins.get(id(key_node))
                child_key_at = location(key_node.start_mark)
                if merge_mark is not None:
                    walk(value_node, data[key], path + (Key(key),),
                            via='merge', used_at=location(merge_mark),
                            key_at=child_key_at)
                else:
                    walk(value_node, data[key], path + (Key(key),),
                            key_at=child_key_at)
        elif isinstance(node, SequenceNode):
            for position, child_node in enumerate(node.value):
                walk(child_node, data[position], path + (Index(position),))

    walk(root_node, root_data, ())


def safe_load_with_index(stream):
    """Safely load a single YAML document, returning ``(data, SourceIndex)``.

    ``data`` is exactly what ``yaml.safe_load`` would return (shared and
    recursive objects keep their identity); the index maps every path in
    the data to its source position.
    """
    loader = IndexedSafeLoader(stream)
    try:
        return loader.get_single_data_with_index()
    finally:
        loader.dispose()


def safe_load_all_with_index(stream):
    """Lazily load all YAML documents, yielding ``(data, SourceIndex)``."""
    loader = IndexedSafeLoader(stream)
    try:
        while loader.check_data():
            yield loader.get_data_with_index()
    finally:
        loader.dispose()
