__all__ = [
    'IncludeSafeLoader',
    'FileIncludeResolver',
    'IncludeError',
    'IncludeResolverError',
    'IncludeBoundaryError',
    'safe_load_with_includes',
    'safe_load_with_include',
    'safe_load_includes',
    'safe_load_include',
    'safe_load_all_with_includes',
    'safe_load_all_with_include',
    'SafeIncludeLoader',
    'FileResolver',
    'LocalFileIncludeResolver',
]

import copy
import os.path

from .error import MarkedYAMLError
from .loader import SafeLoader


INCLUDE_TAG = '!include'
DEFAULT_MAX_INCLUDES = 100
DEFAULT_MAX_INCLUDE_DEPTH = 10


class IncludeError(MarkedYAMLError):
    pass


class IncludeResolverError(IncludeError):
    pass


class IncludeBoundaryError(IncludeResolverError):
    pass


class _IncludeState:

    def __init__(self, resolver, max_includes, max_depth):
        if not callable(resolver):
            raise TypeError("include resolver must be callable")
        if not isinstance(max_includes, int) or isinstance(max_includes, bool):
            raise TypeError("max_includes must be an integer")
        if not isinstance(max_depth, int) or isinstance(max_depth, bool):
            raise TypeError("max_include_depth must be an integer")
        if max_includes < 1:
            raise ValueError("max_includes must be greater than zero")
        if max_depth < 1:
            raise ValueError("max_include_depth must be greater than zero")

        self.resolver = resolver
        self.max_includes = max_includes
        self.max_depth = max_depth
        self.include_count = 0
        self.include_depth = 0
        self.active_sources = []
        self.nodes = {}

    def enter_source(self, source):
        self.active_sources.append(source)

    def leave_source(self):
        self.active_sources.pop()

    def construct_from_source(self, loader, node):
        self.enter_source(loader.include_source)
        try:
            return loader.construct_document(copy.deepcopy(node))
        except MarkedYAMLError as exc:
            raise self.wrap_include_error(exc, loader.include_name,
                    loader.include_mark) from exc
        finally:
            self.leave_source()

    def wrap_include_error(self, exc, name, mark):
        note = str(exc)
        if isinstance(exc, IncludeError):
            error_type = type(exc)
        else:
            error_type = IncludeError
        return error_type("while including %r" % name, mark, None, None,
                note=note)

    def load_include(self, current_source, name, mark):
        if self.include_count >= self.max_includes:
            raise IncludeError(
                "while resolving an !include reference", mark,
                "too many includes (limit is %d)" % self.max_includes, None)
        if self.include_depth >= self.max_depth:
            raise IncludeError(
                "while resolving an !include reference", mark,
                "maximum include depth of %d was exceeded"
                % self.max_depth, None)

        self.include_count += 1
        try:
            resolved = self.resolver(current_source, name)
        except IncludeResolverError as exc:
            raise type(exc)(
                "while resolving !include %r" % name, mark,
                exc.problem or str(exc), exc.problem_mark) from exc
        except Exception as exc:
            raise IncludeResolverError(
                "while resolving !include %r" % name, mark,
                "include resolver raised %s: %s"
                % (type(exc).__name__, exc), None) from exc

        try:
            new_source, text = resolved
        except (TypeError, ValueError) as exc:
            raise IncludeResolverError(
                "while resolving !include %r" % name, mark,
                "include resolver must return a (source, text) pair",
                None) from exc

        try:
            hash(new_source)
        except TypeError as exc:
            raise IncludeResolverError(
                "while resolving !include %r" % name, mark,
                "include source must be hashable", None) from exc
        if not isinstance(text, str):
            raise IncludeResolverError(
                "while resolving !include %r" % name, mark,
                "include text must be a string", None)

        if new_source in self.active_sources:
            cycle = self.active_sources + [new_source]
            raise IncludeError(
                "while resolving !include %r" % name, mark,
                "detected an include cycle: %s"
                % " -> ".join(repr(source) for source in cycle), None)

        self.active_sources.append(new_source)
        self.include_depth += 1
        try:
            try:
                child, node = self.nodes[new_source]
            except KeyError:
                child = IncludeSafeLoader(
                    text, self.resolver, source=new_source,
                    _include_state=self)
                try:
                    node = child.get_single_node()
                    child.dispose()
                except MarkedYAMLError as exc:
                    child.dispose()
                    raise self.wrap_include_error(exc, name, mark) from exc
                child.include_name = name
                child.include_mark = mark
                self.nodes[new_source] = child, node

            child.include_name = name
            child.include_mark = mark
            return self.construct_from_source(child, node)
        finally:
            self.include_depth -= 1
            self.active_sources.pop()


class IncludeSafeLoader(SafeLoader):

    def __init__(self, stream, include_resolver=None, source=None,
            max_includes=DEFAULT_MAX_INCLUDES,
            max_depth=DEFAULT_MAX_INCLUDE_DEPTH,
            max_include_depth=None,
            resolver=None,
            _include_state=None):
        super().__init__(stream)
        self.include_source = source
        if source is not None:
            self.name = str(source)
        if _include_state is None:
            if resolver is not None:
                include_resolver = resolver
            self.include_state = _IncludeState(
                include_resolver, max_includes,
                max_depth if max_include_depth is None else max_include_depth)
        else:
            self.include_state = _include_state

    def get_single_data(self):
        node = self.get_single_node()
        if node is None:
            return None
        self.include_state.enter_source(self.include_source)
        try:
            return self.construct_document(node)
        finally:
            self.include_state.leave_source()

    def get_data(self):
        if not self.check_node():
            return
        node = self.get_node()
        self.include_state.enter_source(self.include_source)
        try:
            return self.construct_document(node)
        finally:
            self.include_state.leave_source()

    def construct_include(self, node):
        name = self.construct_scalar(node)
        return self.include_state.load_include(
            self.include_source, name, node.start_mark)


IncludeSafeLoader.add_constructor(
    INCLUDE_TAG, IncludeSafeLoader.construct_include)
SafeIncludeLoader = IncludeSafeLoader


class FileIncludeResolver:

    def __init__(self, root):
        self.root = self._canonical_root(root)

    def _canonical_root(self, root):
        canonical_root = os.path.realpath(os.fspath(root))
        if not os.path.isdir(canonical_root):
            raise IncludeBoundaryError(None, None,
                    "include root is not a directory: %s" % root, None)
        return canonical_root

    def _within_root(self, path):
        try:
            common_path = os.path.commonpath([self.root, path])
        except ValueError as exc:
            raise IncludeBoundaryError(
                None, None,
                "include path is outside the configured root: %s" % path,
                None) from exc
        if common_path != self.root:
            raise IncludeBoundaryError(
                    None, None,
                    "include path escapes the configured root: %s" % path,
                    None)
        return path

    def _resolve_within_root(self, path):
        path = os.path.realpath(os.fspath(path))
        return self._within_root(path)

    def __call__(self, source, name):
        if source is None:
            source_directory = self.root
        else:
            source_path = os.fspath(source)
            if not os.path.isabs(source_path):
                source_path = os.path.join(self.root, source_path)
            source_path = self._resolve_within_root(source_path)
            source_directory = os.path.dirname(source_path)

        include_path = os.fspath(name)
        if not os.path.isabs(include_path):
            include_path = os.path.join(source_directory, include_path)
        include_path = self._resolve_within_root(include_path)

        try:
            with open(include_path, encoding='utf-8') as stream:
                text = stream.read()
        except Exception as exc:
            raise IncludeResolverError(str(exc)) from exc
        return include_path, text


def safe_load_with_includes(stream, include_resolver=None, source=None,
        max_includes=DEFAULT_MAX_INCLUDES,
        max_depth=DEFAULT_MAX_INCLUDE_DEPTH,
        max_include_depth=None, resolver=None):
    if resolver is not None:
        include_resolver = resolver
    loader = IncludeSafeLoader(
        stream, include_resolver, source=source,
        max_includes=max_includes,
        max_depth=max_depth if max_include_depth is None
        else max_include_depth)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def safe_load_all_with_includes(stream, include_resolver=None, source=None,
        max_includes=DEFAULT_MAX_INCLUDES,
        max_depth=DEFAULT_MAX_INCLUDE_DEPTH,
        max_include_depth=None, resolver=None):
    if resolver is not None:
        include_resolver = resolver
    loader = IncludeSafeLoader(
        stream, include_resolver, source=source,
        max_includes=max_includes,
        max_depth=max_depth if max_include_depth is None
        else max_include_depth)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


safe_load_includes = safe_load_with_includes
safe_load_with_include = safe_load_with_includes
safe_load_include = safe_load_with_includes
safe_load_all_with_include = safe_load_all_with_includes
FileResolver = FileIncludeResolver
LocalFileIncludeResolver = FileIncludeResolver
