
__all__ = [
    'BaseLoader', 'FullLoader', 'SafeLoader', 'Loader', 'UnsafeLoader',
    'ResourceBudget', 'ResourceLimitError',
]

from .reader import *
from .scanner import *
from .parser import *
from .composer import *
from .constructor import *
from .resolver import *
from .resource import ResourceBudget, ResourceLimitError, _ResourceBudgetTracker


DEFAULT_SAFE_DOCUMENT_BUDGET = ResourceBudget(
        nested_depth=400,
        scalar_length=1_000_000,
        node_count=100_000,
        alias_references=10_000,
)

DEFAULT_SAFE_STREAM_BUDGET = ResourceBudget(
        nested_depth=400,
        scalar_length=10_000_000,
        node_count=1_000_000,
        alias_references=100_000,
)

class BaseLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):

    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)

class FullLoader(Reader, Scanner, Parser, Composer, FullConstructor, Resolver):

    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        FullConstructor.__init__(self)
        Resolver.__init__(self)

class SafeLoader(Reader, Scanner, Parser, Composer, SafeConstructor, Resolver):

    def __init__(self, stream, document_budget=None, stream_budget=None):
        if document_budget is None:
            document_budget = DEFAULT_SAFE_DOCUMENT_BUDGET
        if stream_budget is None:
            stream_budget = DEFAULT_SAFE_STREAM_BUDGET
        self.resource_tracker = _ResourceBudgetTracker(
                document_budget, stream_budget)
        Reader.__init__(self, stream)
        Scanner.__init__(self, self.resource_tracker)
        Parser.__init__(self)
        Composer.__init__(self, self.resource_tracker)
        SafeConstructor.__init__(self)
        Resolver.__init__(self)

    def dispose(self):
        Scanner.dispose(self)
        Parser.dispose(self)
        Composer.dispose(self)
        BaseConstructor.dispose(self)
        self.resource_tracker.begin_document()

class Loader(Reader, Scanner, Parser, Composer, Constructor, Resolver):

    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        Constructor.__init__(self)
        Resolver.__init__(self)

# UnsafeLoader is the same as Loader (which is and was always unsafe on
# untrusted input). Use of either Loader or UnsafeLoader should be rare, since
# FullLoad should be able to load almost all YAML safely. Loader is left intact
# to ensure backwards compatibility.
class UnsafeLoader(Reader, Scanner, Parser, Composer, Constructor, Resolver):

    def __init__(self, stream):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        Constructor.__init__(self)
        Resolver.__init__(self)
