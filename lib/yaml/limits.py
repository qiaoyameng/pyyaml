__all__ = ['ResourceLimits', 'ResourceLimitError']

from .error import MarkedYAMLError


class ResourceLimitError(MarkedYAMLError):
    """Raised when a resource budget is exceeded.

    This fires while the input is still being scanned or composed, so an
    oversized document is never fully built before the limit is enforced.
    """

    CATEGORY_DEPTH = 'depth'
    CATEGORY_SCALAR_LENGTH = 'scalar length'
    CATEGORY_NODES = 'nodes'
    CATEGORY_ALIASES = 'aliases'

    def __init__(self, category, scope, limit, usage, mark=None):
        self.category = category
        self.scope = scope
        self.limit = limit
        self.usage = usage
        where = "in a single document" if scope == 'document' \
                else "across the whole stream"
        problem = ("resource limit exceeded: %s %s (limit %d, used %d)"
                   % (category, where, limit, usage))
        super().__init__(context=None, context_mark=None,
                         problem=problem, problem_mark=mark, note=None)


class ResourceLimits:
    """Resource budgets for loading untrusted YAML.

    Four budgets are tracked independently:

    * ``max_depth`` -- nesting depth of collections (charged while composing
      before descending into children);
    * ``max_scalar_length`` -- length of any single scalar in characters
      (charged while scanning, before the scalar value is assembled);
    * ``max_nodes`` -- number of unique nodes, i.e. node definitions rather
      than alias references (charged while composing);
    * ``max_aliases`` -- number of alias references (charged when an
      ``AliasEvent`` is composed). Alias references and unique nodes are
      metered separately.

    The ``stream_*`` arguments bound cumulative usage across every document
    in a stream (``load_all``) and reset only when the loader is disposed.
    Depth has no stream-wide counterpart.

    A value of ``None`` disables the corresponding budget.
    """

    DEFAULT_MAX_DEPTH = 256
    DEFAULT_MAX_SCALAR_LENGTH = 3 * 1024 * 1024
    DEFAULT_MAX_NODES = 100000
    DEFAULT_MAX_ALIASES = 10000

    DEFAULT_STREAM_SCALAR_LENGTH = 30 * 1024 * 1024
    DEFAULT_STREAM_NODES = 1000000
    DEFAULT_STREAM_ALIASES = 100000

    # Sentinel distinguishes "use the built-in default" from an explicit
    # ``None`` (which disables that budget).
    _DEFAULT = object()

    def __init__(self,
            max_depth=_DEFAULT,
            max_scalar_length=_DEFAULT,
            max_nodes=_DEFAULT,
            max_aliases=_DEFAULT,
            stream_max_scalar_length=_DEFAULT,
            stream_max_nodes=_DEFAULT,
            stream_max_aliases=_DEFAULT):
        defaults = {
            'max_depth': self.DEFAULT_MAX_DEPTH,
            'max_scalar_length': self.DEFAULT_MAX_SCALAR_LENGTH,
            'max_nodes': self.DEFAULT_MAX_NODES,
            'max_aliases': self.DEFAULT_MAX_ALIASES,
            'stream_max_scalar_length': self.DEFAULT_STREAM_SCALAR_LENGTH,
            'stream_max_nodes': self.DEFAULT_STREAM_NODES,
            'stream_max_aliases': self.DEFAULT_STREAM_ALIASES,
        }
        values = locals()
        for name, default in defaults.items():
            value = values[name]
            setattr(self, name, default if value is self._DEFAULT else value)

    @classmethod
    def unlimited(cls):
        """Return limits that never trigger."""
        return cls(None, None, None, None, None, None, None)

    def any_active(self):
        return any(value is not None for value in (
            self.max_depth, self.max_scalar_length, self.max_nodes,
            self.max_aliases, self.stream_max_scalar_length,
            self.stream_max_nodes, self.stream_max_aliases))


class _ResourceBudget:
    """Mutable counters shared by the scanner and composer."""

    def __init__(self, limits=None):
        if limits is None:
            limits = ResourceLimits()
        self.limits = limits

        # Per-document counters, reset between documents of a stream.
        self.document_depth = 0
        self.document_nodes = 0
        self.document_aliases = 0
        self.document_scalar = 0

        # Whole-stream counters, reset only on disposal.
        self.stream_nodes = 0
        self.stream_aliases = 0
        self.stream_scalar = 0

    def reset_document(self):
        # Called when a document finishes (normally or with an error). This
        # drops the per-document temporary counters; the composer releases
        # its anchor table separately.
        self.document_depth = 0
        self.document_nodes = 0
        self.document_aliases = 0
        self.document_scalar = 0

    def reset_stream(self):
        self.reset_document()
        self.stream_nodes = 0
        self.stream_aliases = 0
        self.stream_scalar = 0

    def begin_scalar(self):
        # The per-document scalar budget applies to each individual scalar.
        self.document_scalar = 0

    def charge_scalar(self, amount, mark=None):
        if amount <= 0:
            return
        self.document_scalar += amount
        limit = self.limits.max_scalar_length
        if limit is not None and self.document_scalar > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_SCALAR_LENGTH, 'document',
                    limit, self.document_scalar, mark)
        self.stream_scalar += amount
        limit = self.limits.stream_max_scalar_length
        if limit is not None and self.stream_scalar > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_SCALAR_LENGTH, 'stream',
                    limit, self.stream_scalar, mark)

    def enter_collection(self, mark=None):
        self.document_depth += 1
        limit = self.limits.max_depth
        if limit is not None and self.document_depth > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_DEPTH, 'document',
                    limit, self.document_depth, mark)

    def leave_collection(self):
        self.document_depth -= 1

    def charge_node(self, mark=None):
        self.document_nodes += 1
        limit = self.limits.max_nodes
        if limit is not None and self.document_nodes > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_NODES, 'document',
                    limit, self.document_nodes, mark)
        self.stream_nodes += 1
        limit = self.limits.stream_max_nodes
        if limit is not None and self.stream_nodes > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_NODES, 'stream',
                    limit, self.stream_nodes, mark)

    def charge_alias(self, mark=None):
        # Alias references are metered separately from unique nodes.
        self.document_aliases += 1
        limit = self.limits.max_aliases
        if limit is not None and self.document_aliases > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_ALIASES, 'document',
                    limit, self.document_aliases, mark)
        self.stream_aliases += 1
        limit = self.limits.stream_max_aliases
        if limit is not None and self.stream_aliases > limit:
            raise ResourceLimitError(
                    ResourceLimitError.CATEGORY_ALIASES, 'stream',
                    limit, self.stream_aliases, mark)
