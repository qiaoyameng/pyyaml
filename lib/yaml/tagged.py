__all__ = ['TaggedValue']

import reprlib


class TaggedValue:
    """A scalar, sequence, or mapping with an unrecognized YAML tag."""

    __slots__ = ('tag', 'value')

    def __init__(self, tag, value):
        self.tag = tag
        self.value = value

    def __repr__(self):
        return '%s(tag=%r, value=%s)' % (
            self.__class__.__name__, self.tag, reprlib.repr(self.value))
