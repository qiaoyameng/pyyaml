__all__ = ['ResourceBudget', 'ResourceLimitError']

from .error import MarkedYAMLError


class ResourceLimitError(MarkedYAMLError):

    def __init__(self, category, stage, limit, used, mark, scope='document'):
        self.category = category
        self.stage = stage
        self.limit = limit
        self.used = used
        self.mark = mark
        self.scope = scope
        problem = "%s resource usage (%d) exceeded the %s limit (%d) while %s" % (
                scope, used, category, limit, stage)
        super().__init__(None, None, problem, mark)


class ResourceBudget:
    """Resource limits for one document or an entire YAML stream.

    Scalar length is charged while scanning. Nested depth, unique node count,
    and alias reference count are charged while composing representation nodes.
    Construction does not introduce a separate quota; it clears per-document
    state after construction or when a limit is exceeded.
    """

    __slots__ = [
            'nested_depth',
            'scalar_length',
            'node_count',
            'alias_references',
    ]

    def __init__(self, nested_depth=None, scalar_length=None,
            node_count=None, alias_references=None):
        self.nested_depth = self._limit(nested_depth)
        self.scalar_length = self._limit(scalar_length)
        self.node_count = self._limit(node_count)
        self.alias_references = self._limit(alias_references)

    @classmethod
    def unlimited(cls):
        budget = cls()
        budget.nested_depth = -1
        budget.scalar_length = -1
        budget.node_count = -1
        budget.alias_references = -1
        return budget

    @staticmethod
    def _limit(value):
        if value is None:
            return -1
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("resource limits must be non-negative integers")
        return value


class _ResourceBudgetState:

    __slots__ = [
            'nested_depth',
            'scalar_length',
            'node_count',
            'alias_references',
    ]

    def __init__(self):
        self.nested_depth = 0
        self.scalar_length = 0
        self.node_count = 0
        self.alias_references = 0


class _ResourceBudgetTracker:

    def __init__(self, document_budget, stream_budget):
        self.document_budget = document_budget
        self.stream_budget = stream_budget
        self.document = _ResourceBudgetState()
        self.stream = _ResourceBudgetState()

    def begin_document(self):
        self.document = _ResourceBudgetState()

    def release_document(self):
        self.begin_document()

    def charge_scalar(self, length, mark):
        self._charge('scalar_length', 'scanning', length, mark)

    def enter_node(self, container, mark):
        if container:
            self.charge_nested_depth(mark)
        self.charge_node(mark)

    def leave_node(self, container):
        if container:
            self.document.nested_depth -= 1

    def charge_nested_depth(self, mark):
        document_used = self.document.nested_depth + 1
        stream_used = max(self.stream.nested_depth, document_used)
        document_limit = self.document_budget.nested_depth
        stream_limit = self.stream_budget.nested_depth
        if document_limit >= 0 and document_used > document_limit:
            raise ResourceLimitError('nested_depth', 'composing',
                    document_limit, document_used, mark, 'document')
        if stream_limit >= 0 and stream_used > stream_limit:
            raise ResourceLimitError('nested_depth', 'composing',
                    stream_limit, stream_used, mark, 'stream')
        self.document.nested_depth = document_used
        self.stream.nested_depth = stream_used

    def charge_node(self, mark):
        self._charge('node_count', 'composing', 1, mark)

    def charge_alias(self, mark):
        self._charge('alias_references', 'composing', 1, mark)

    def _charge(self, category, stage, amount, mark):
        document_used = getattr(self.document, category) + amount
        stream_used = getattr(self.stream, category) + amount
        document_limit = getattr(self.document_budget, category)
        stream_limit = getattr(self.stream_budget, category)
        if document_limit >= 0 and document_used > document_limit:
            raise ResourceLimitError(category, stage, document_limit,
                    document_used, mark, 'document')
        if stream_limit >= 0 and stream_used > stream_limit:
            raise ResourceLimitError(category, stage, stream_limit,
                    stream_used, mark, 'stream')
        setattr(self.document, category, document_used)
        setattr(self.stream, category, stream_used)
