"""
Source-indexed safe loading.

This module provides safe loading entry points that, in addition to the
plain Python data, produce a separate source index: position metadata
mapping every value of the loaded document(s) back to the line and
column in the original YAML stream.  The data itself is untouched, so
upper layers can report where a problematic value came from.

The index covers mapping keys, mapping values and sequence items.  A
path is a tuple of segments: a constructed mapping key (usually a
string) addresses a mapping value, an integer addresses a sequence
item, so string keys and numeric indices can never be confused.

Anchors/aliases and merge keys are represented as references: for each
of them the index stores both the definition position and the usage
position instead of copying the shared subtree.  This keeps shared
objects as single index entries and makes recursive aliases finite.
Every entry is tagged with the number of the document it belongs to.
"""

__all__ = [
    'Position',
    'NodeInfo',
    'SourceIndex',
    'SourceIndexLoader',
    'safe_load_with_index',
    'safe_load_all_with_index',
]

from .composer import Composer, ComposerError
from .constructor import SafeConstructor
from .events import AliasEvent
from .nodes import Node, SequenceNode, MappingNode
from .parser import Parser
from .reader import Reader
from .resolver import Resolver
from .scanner import Scanner

_MERGE_TAG = 'tag:yaml.org,2002:merge'

_FAILED = object()


class Position:
    """A position in the YAML stream (1-based line and column)."""

    __slots__ = ('mark',)

    def __init__(self, mark):
        self.mark = mark

    @property
    def name(self):
        return self.mark.name

    @property
    def index(self):
        return self.mark.index

    @property
    def line(self):
        return self.mark.line + 1

    @property
    def column(self):
        return self.mark.column + 1

    def __eq__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return self.mark is other.mark or (
                self.mark.name == other.mark.name
                and self.mark.index == other.mark.index)

    def __hash__(self):
        return hash((self.mark.name, self.mark.index))

    def __repr__(self):
        return 'Position(line=%d, column=%d)' % (self.line, self.column)


class NodeInfo:
    """Position metadata for a single value of a loaded document.

    ``document`` is the 0-based document number, ``path`` the tuple of
    segments addressing the value within that document and ``kind`` one
    of ``'scalar'``, ``'sequence'`` or ``'mapping'``.  ``origin`` is one
    of:

    - ``NodeInfo.DEFINITION``: the value is defined at this path.
    - ``NodeInfo.ALIAS``: the value is shared through an alias;
      ``target`` is the path of its definition and ``usage`` the
      position of the alias.
    - ``NodeInfo.MERGE``: the value entered the mapping through a
      ``<<`` merge key; ``target`` is the path of its definition (when
      the merge source has one), ``usage`` the position of the
      outermost merge site and ``via`` the positions of the whole
      merge chain, outermost first.
    """

    DEFINITION = 'definition'
    ALIAS = 'alias'
    MERGE = 'merge'

    def __init__(self, document, path, kind, start_mark, end_mark,
            key_start_mark, key_end_mark):
        self.document = document
        self.path = path
        self.kind = kind
        self.origin = self.DEFINITION
        self.target = None
        self.usage = None
        self.via = ()
        self.start = Position(start_mark) if start_mark is not None else None
        self.end = Position(end_mark) if end_mark is not None else None
        self.key_start = (Position(key_start_mark)
                if key_start_mark is not None else None)
        self.key_end = (Position(key_end_mark)
                if key_end_mark is not None else None)

    def __repr__(self):
        return '%s(path=%r, document=%r, kind=%r, origin=%r)' % (
                self.__class__.__name__, self.path, self.document,
                self.kind, self.origin)


class SourceIndex:
    """Position metadata for one or more loaded documents.

    Entries are keyed by ``(document, path)`` where ``path`` is a tuple
    of mapping keys (strings or other constructed key objects) and
    sequence indices (integers).
    """

    def __init__(self):
        self._entries = {}
        self.document_count = 0

    def entry(self, path, document=0):
        """Return the NodeInfo stored exactly at *path*, or None.

        Alias and merge references are returned as stored; use
        ``resolve()`` to follow them to the definition.
        """
        return self._entries.get((document, tuple(path)))

    def resolve(self, path, document=0):
        """Return the NodeInfo of the definition for *path*.

        Alias and merge references are followed to the entry that
        defines the value.  Recursive references are detected and
        reported as the entry at the point of recursion instead of
        being expanded into an infinite path.  Returns None if no
        entry covers *path*.
        """
        rest = tuple(path)
        seen = set()
        while True:
            if (document, rest) in seen:
                return self._entries.get((document, rest))
            seen.add((document, rest))
            info = self._entries.get((document, rest))
            if info is not None:
                if info.target is None:
                    return info
                rest = tuple(info.target)
                continue
            for end in range(len(rest)-1, 0, -1):
                ancestor = self._entries.get((document, rest[:end]))
                if ancestor is not None and ancestor.target is not None:
                    rest = tuple(ancestor.target) + rest[end:]
                    break
            else:
                return None

    def __contains__(self, path):
        return (0, tuple(path)) in self._entries

    def __len__(self):
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries.values())


class _SourceIndexComposer(Composer):

    def __init__(self):
        super().__init__()
        self.alias_uses = {}

    def compose_document(self):
        self.alias_uses = {}
        return super().compose_document()

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            event = self.get_event()
            anchor = event.anchor
            if anchor not in self.anchors:
                raise ComposerError(None, None, "found undefined alias %r"
                        % anchor, event.start_mark)
            node = self.anchors[anchor]
            self.alias_uses.setdefault((parent, index), []).append(
                    (node, event.start_mark, event.end_mark))
            return node
        return super().compose_node(parent, index)


class SourceIndexLoader(Reader, Scanner, Parser, _SourceIndexComposer,
        SafeConstructor, Resolver):
    """A SafeLoader variant that additionally builds a SourceIndex.

    The constructed data is identical to what SafeLoader produces,
    including object sharing through anchors and aliases.
    """

    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        _SourceIndexComposer.__init__(self)
        SafeConstructor.__init__(self)
        Resolver.__init__(self)
        self.source_index = SourceIndex()

    def construct_document(self, node):
        # The index is built from the untouched node graph, before
        # construction flattens merge keys in place.
        _IndexBuilder(self, node).build()
        return super().construct_document(node)


class _IndexBuilder:

    def __init__(self, loader, root):
        self.index = loader.source_index
        self.root = root
        self.alias_uses = loader.alias_uses
        self.document = self.index.document_count
        self.index.document_count += 1
        self.definitions = {}
        self.key_constructor = SafeConstructor()
        self.constructed_keys = {}

    def build(self):
        self._walk_node(self.root, None, None, (), None)

    def _walk_node(self, node, parent, index, path, key_node):
        info = self._add_entry(node, path, key_node)
        node_id = id(node)
        if node_id in self.definitions:
            # A shared node can only be reached through an alias: keep a
            # single reference entry instead of copying the subtree.
            info.origin = NodeInfo.ALIAS
            info.target = self.definitions[node_id]
            use = self._alias_use(parent, index)
            if use is not None:
                info.usage = Position(use[1])
            return
        self.definitions[node_id] = path
        self._walk_children(node, path)

    def _walk_children(self, node, path):
        if isinstance(node, SequenceNode):
            for item_index, child in enumerate(node.value):
                self._walk_node(child, node, item_index,
                        path + (item_index,), None)
        elif isinstance(node, MappingNode):
            self._walk_mapping(node, path)

    def _walk_mapping(self, node, path):
        final = {}
        for pair in self._flatten_pairs(node):
            key = self._construct_key(pair[0])
            if key is _FAILED:
                continue
            try:
                final[key] = pair
            except TypeError:
                continue
        merge_key_ids = set()
        for key_node, value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                contributions = self._merge_value_pairs(
                        value_node, node, key_node, ())
                for k_node, v_node, source, via in contributions:
                    if id(k_node.value) in merge_key_ids:
                        continue
                    merge_key_ids.add(id(k_node.value))
                    key = self._construct_key(k_node)
                    if key is _FAILED:
                        continue
                    try:
                        winner = final.get(key)
                    except TypeError:
                        continue
                    if winner is None or winner[0] is not k_node:
                        continue
                    self._add_merged_entry(
                            k_node, v_node, source, via, path, key)
            else:
                key = self._construct_key(key_node)
                if key is _FAILED:
                    continue
                try:
                    winner = final.get(key)
                except TypeError:
                    continue
                if winner is None or winner[0] is not key_node:
                    continue
                self._walk_node(value_node, node, key_node,
                        path + (key,), key_node)

    def _add_merged_entry(self, key_node, value_node, source, via, path, key):
        child_path = path + (key,)
        info = self._add_entry(value_node, child_path, key_node)
        info.origin = NodeInfo.MERGE
        info.via = tuple(position for position in
                (self._hop_position(hop) for hop in via)
                if position is not None)
        if info.via:
            info.usage = info.via[0]
        source_id = id(source)
        if source_id not in self.definitions:
            # An inline merge source has no path of its own.
            self.definitions[source_id] = None
        source_path = self.definitions[source_id]
        if source_path is not None:
            info.target = source_path + (key,)
        value_id = id(value_node)
        if value_id in self.definitions:
            if info.target is None:
                info.target = self.definitions[value_id]
            return
        self.definitions[value_id] = child_path
        self._walk_children(value_node, child_path)

    def _flatten_pairs(self, node, via=(), active=()):
        # Mirror SafeConstructor.flatten_mapping without mutating the
        # node: merged pairs come first, local pairs keep their order.
        if id(node) in active:
            # Recursive merge: the real constructor removes merge keys
            # as it flattens, so only the local pairs remain visible.
            return [(key_node, value_node, node, via)
                    for key_node, value_node in node.value
                    if key_node.tag != _MERGE_TAG]
        active = active + (id(node),)
        merge = []
        merge_key_ids = set()
        local = []
        for key_node, value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                pairs = self._merge_value_pairs(
                        value_node, node, key_node, via, active)
                for pair in pairs:
                    if id(pair[0].value) not in merge_key_ids:
                        merge_key_ids.add(id(pair[0].value))
                        merge.append(pair)
            else:
                local.append((key_node, value_node, node, via))
        return merge + local

    def _merge_value_pairs(self, value_node, parent, key_node, via, active=()):
        if isinstance(value_node, MappingNode):
            return self._flatten_pairs(value_node,
                    via + ((parent, key_node),), active)
        if isinstance(value_node, SequenceNode):
            pairs = []
            for item_index, subnode in enumerate(value_node.value):
                if isinstance(subnode, MappingNode):
                    pairs.extend(self._flatten_pairs(subnode,
                            via + ((value_node, item_index),), active))
            return pairs
        return []

    def _add_entry(self, node, path, key_node):
        info = NodeInfo(
                document=self.document,
                path=path,
                kind=node.id,
                start_mark=node.start_mark,
                end_mark=node.end_mark,
                key_start_mark=(key_node.start_mark
                        if key_node is not None else None),
                key_end_mark=(key_node.end_mark
                        if key_node is not None else None))
        self.index._entries[(self.document, path)] = info
        return info

    def _alias_use(self, parent, index):
        uses = self.alias_uses.get((parent, index))
        if uses:
            return uses[0]
        return None

    def _hop_position(self, hop):
        parent, index = hop
        use = self._alias_use(parent, index)
        if use is not None:
            return Position(use[1])
        if isinstance(index, Node):
            if index.start_mark is not None:
                return Position(index.start_mark)
        elif parent.start_mark is not None:
            return Position(parent.start_mark)
        return None

    def _construct_key(self, key_node):
        node_id = id(key_node)
        if node_id not in self.constructed_keys:
            try:
                self.constructed_keys[node_id] = \
                        self.key_constructor.construct_object(key_node)
            except Exception:
                self.constructed_keys[node_id] = _FAILED
        return self.constructed_keys[node_id]


def safe_load_with_index(stream):
    """
    Parse the first YAML document in a stream, produce the
    corresponding Python object and a source index for it.

    Return a ``(data, index)`` tuple.  The data is identical to what
    ``safe_load`` produces, including object sharing through anchors
    and aliases.  Resolve only basic YAML tags, so this is safe for
    untrusted input.
    """
    loader = SourceIndexLoader(stream)
    try:
        return loader.get_single_data(), loader.source_index
    finally:
        loader.dispose()

def safe_load_all_with_index(stream):
    """
    Parse all YAML documents in a stream, produce the corresponding
    Python objects and a source index covering all of them.

    Return a ``(data, index)`` tuple where ``data`` is the list of
    document objects.  Index entries carry the document number.
    Resolve only basic YAML tags, so this is safe for untrusted input.
    """
    loader = SourceIndexLoader(stream)
    try:
        data = []
        while loader.check_data():
            data.append(loader.get_data())
        return data, loader.source_index
    finally:
        loader.dispose()
