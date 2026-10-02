__all__ = ['TaggedValue']


class TaggedValue:
    def __init__(self, tag, value):
        self.tag = tag
        self.value = value

    def __repr__(self):
        return '%s(%r, %r)' % (self.__class__.__name__, self.tag, self.value)

    def __eq__(self, other):
        if not isinstance(other, TaggedValue):
            return NotImplemented
        return self.tag == other.tag and self.value == other.value

    def __hash__(self):
        return hash((self.tag, self.value))
