
__all__ = ['Pairs']


def _typed_equal(first, second):
    # YAML-aware equality: objects of different YAML-derived Python types
    # (e.g. ``1`` and ``True``) are never equal, even when ``==`` says so.
    if type(first) is not type(second):
        return False
    if isinstance(first, Pairs):
        if len(first) != len(second):
            return False
        return all(
                _typed_equal(first_key, second_key)
                and _typed_equal(first_value, second_value)
                for (first_key, first_value), (second_key, second_value)
                in zip(first, second))
    if isinstance(first, (list, tuple)):
        if len(first) != len(second):
            return False
        return all(_typed_equal(first_item, second_item)
                for first_item, second_item in zip(first, second))
    return first == second


class Pairs:
    """Ordered key-value entries of a YAML mapping.

    Unlike a ``dict``, this representation preserves complex keys
    (sequences, mappings), duplicate keys and entry order exactly as
    they appear in the document.  Keys and values are ordinary Python
    objects produced by the constructor; they are never converted to
    their ``repr`` strings.

    Entry lookup (``get``, ``in``) compares keys with YAML-aware
    equality: keys must have the same type *and* compare equal, so the
    YAML keys ``1`` (int) and ``true`` (bool) stay distinct even though
    ``1 == True`` in Python.  Comparison recurses into nested ``Pairs``,
    lists and tuples.  When a key occurs multiple times, the first
    matching entry wins.
    """

    def __init__(self, entries=()):
        self._entries = []
        self.extend(entries)

    def append(self, entry):
        key, value = entry
        self._entries.append((key, value))

    def extend(self, entries):
        for entry in entries:
            self.append(entry)

    def keys(self):
        return [key for key, value in self._entries]

    def values(self):
        return [value for key, value in self._entries]

    def items(self):
        return list(self._entries)

    def get(self, key, default=None):
        """Return the value of the first entry whose key matches ``key``
        under YAML-aware equality, or ``default`` if there is none."""
        for entry_key, entry_value in self._entries:
            if _typed_equal(entry_key, key):
                return entry_value
        return default

    def __contains__(self, key):
        return any(_typed_equal(entry_key, key)
                for entry_key, entry_value in self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __len__(self):
        return len(self._entries)

    def __getitem__(self, index):
        return self._entries[index]

    def __eq__(self, other):
        if isinstance(other, Pairs):
            return _typed_equal(self, other)
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self._entries)
