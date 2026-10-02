"""
Safe ``!include`` support.

This module adds a single, opt-in YAML tag, ``!include``.  It does not enable
any of the arbitrary Python object tags; the loader is built on
:class:`SafeLoader`.

The text behind an include is never guessed from disk or from any other
implicit source.  The caller supplies a *resolver* callable::

    def resolver(current_source, include_name):
        return new_source, text

* ``current_source`` is ``None`` for the top-level document and otherwise the
  source identifier returned for the document currently being constructed.
* ``include_name`` is the string argument of the ``!include`` tag.
* The return value is a tuple of the new source identifier and the YAML text.

The library itself enforces a total include count, an include depth and
detects include cycles.

Two entry points are provided:

* :class:`IncludeLoader`, a loader class usable like any other loader.
* :func:`safe_load_include` / :func:`safe_load_all_include`, convenience
  functions.

:class:`FileIncludeResolver` is a resolver that reads files from explicitly
configured root directories.  It canonicalises every path and resolves
symlinks, so a reference can never escape a root.
"""

__all__ = ['IncludeLoader', 'IncludeError', 'FileIncludeResolver',
           'safe_load_include', 'safe_load_all_include']

import copy
import os

from pathlib import Path

from .error import YAMLError
from .loader import SafeLoader
from .nodes import ScalarNode


INCLUDE_TAG = '!include'

DEFAULT_MAX_INCLUDES = 100
DEFAULT_MAX_DEPTH = 10


class IncludeError(YAMLError):
    """An error involving one or more ``!include`` tags.

    The chain of include locations leading to the failure is attached as a
    list of ``(source, name, mark)`` frames, outermost first, so the reported
    error connects the rejected reference back to where it occurred.
    """

    def __init__(self, problem, frames=(), cause=None):
        self.problem = problem
        self.frames = list(frames)
        if cause is not None:
            self.__cause__ = cause

    def add_frame(self, source, name, mark):
        # Frames are kept outermost first, so outer include sites are
        # prepended as the error unwinds through them.
        self.frames.insert(0, (source, name, mark))

    def __str__(self):
        lines = []
        for source, name, mark in self.frames:
            lines.append('while including %r%s'
                    % (name, _format_mark(source, mark)))
        problem = self.problem
        cause_text = str(self.__cause__) if self.__cause__ is not None else ''
        if problem and not problem == cause_text:
            lines.append(problem)
        elif cause_text:
            lines.append(cause_text)
        if cause_text and cause_text != problem:
            lines.append('caused by: %s' % cause_text)
        return '\n'.join(lines)


def _format_mark(source, mark):
    if mark is not None:
        return ' (in %r, line %d, column %d)' \
                % (source if source is not None else mark.name,
                        mark.line + 1, mark.column + 1)
    if source is not None:
        return ' (in %r)' % (source,)
    return ''


class _IncludeState(object):

    def __init__(self, resolver, source, max_includes, max_depth):
        self.resolver = resolver
        self.root_source = source
        self.max_includes = max_includes
        self.max_depth = max_depth
        self.include_count = 0
        # Sources on the active include chain, for cycle detection.
        self.active_sources = []
        # Parsed representation trees keyed by resolved source.
        self.parsed = {}
        # Source of the node currently being constructed (None for the
        # top-level document).  Used when an included document itself contains
        # includes.
        self.construction_sources = []
        # Active !include frames, outermost first.  A frame is pushed before
        # an included document is parsed or constructed and popped afterwards,
        # so any raised error can be annotated with the full include chain.
        self.frame_stack = []


class IncludeLoader(SafeLoader):
    """A :class:`SafeLoader` subclass that supports the ``!include`` tag.

    The tag argument must be a plain string; the provided *resolver* maps it
    to a new source identifier and YAML text.  At most *max_includes* tags are
    resolved in total and no include chain may exceed *max_depth* levels.
    """

    def __init__(self, stream, resolver, source=None,
            max_includes=DEFAULT_MAX_INCLUDES,
            max_depth=DEFAULT_MAX_DEPTH, _state=None):
        SafeLoader.__init__(self, stream)
        if _state is None:
            if resolver is None:
                raise ValueError("IncludeLoader requires a resolver")
            if source is None:
                source = self.name
            state = _IncludeState(resolver, source, max_includes, max_depth)
        else:
            state = _state
        self._include_state = state

    def _construct_include(self, node):
        if not isinstance(node, ScalarNode):
            raise IncludeError(
                    "the !include argument must be a scalar string, "
                    "but found %s" % node.id)
        state = self._include_state
        name = self.construct_scalar(node)
        frame = (state.construction_sources[-1]
                if state.construction_sources
                else state.root_source, name, node.start_mark)
        state.frame_stack.append(frame)
        try:
            if state.include_count >= state.max_includes:
                raise IncludeError(
                        "too many !include references: limit of %d reached"
                        % state.max_includes)
            if len(state.active_sources) >= state.max_depth:
                raise IncludeError(
                        "!include depth limit of %d exceeded"
                        % state.max_depth)
            state.include_count += 1

            current_source = frame[0]
            try:
                resolved = state.resolver(current_source, name)
            except IncludeError:
                raise
            except Exception as exc:
                raise IncludeError(
                        "resolver failed for %r" % name, cause=exc)
            try:
                new_source, text = resolved
            except (TypeError, ValueError) as exc:
                raise IncludeError(
                        "resolver for %r must return a (source, text) pair"
                        % name, cause=exc)
            if not isinstance(text, str):
                raise IncludeError(
                        "resolver for %r must return YAML text as str" % name)

            if new_source == state.root_source or \
                    new_source in state.active_sources:
                cycle = [state.root_source] + state.active_sources \
                        + [new_source]
                raise IncludeError(
                        "circular !include detected: %s"
                        % " -> ".join(repr(item) for item in cycle))

            state.active_sources.append(new_source)
            try:
                if new_source in state.parsed:
                    included_node = state.parsed[new_source]
                else:
                    included_node = self._parse_include(new_source, text)
                    state.parsed[new_source] = included_node

                if included_node is None:
                    return None
                state.construction_sources.append(new_source)
                try:
                    # Each !include gets an independent deep copy; mutating
                    # one expansion must never affect another expansion of the
                    # same source (the node may be cache-reused).
                    data = self.construct_object(included_node, deep=True)
                    data = copy.deepcopy(data)
                except IncludeError:
                    raise
                except YAMLError as exc:
                    raise IncludeError(str(exc), cause=exc)
                finally:
                    state.construction_sources.pop()
            finally:
                state.active_sources.remove(new_source)
            return data
        except IncludeError as exc:
            # Deeper failures already carry the inner frames; this level's
            # own failures carry none yet.  Prepend this frame exactly once.
            if not any(existing is frame for existing in exc.frames):
                exc.add_frame(*frame)
            raise
        finally:
            state.frame_stack.pop()

    def _parse_include(self, source, text):
        sub_loader = IncludeLoader(text, resolver=None, source=source,
                _state=self._include_state)
        sub_loader.name = source
        try:
            return sub_loader.get_single_node()
        except IncludeError:
            raise
        except YAMLError as exc:
            # frame_stack already holds every active include site, including
            # the one that triggered this (possibly lazily driven) parse.
            raise IncludeError(str(exc),
                    frames=list(self._include_state.frame_stack), cause=exc)
        finally:
            sub_loader.dispose()

    @classmethod
    def add_include_constructor(cls):
        cls.add_constructor(INCLUDE_TAG, cls._construct_include)


IncludeLoader.add_include_constructor()


class FileIncludeResolver(object):
    """Resolve ``!include`` names as files under explicit root directories.

    Every reference is joined onto the directory of the current source (or
    onto the first root for top-level documents) and the resulting path is
    canonicalised.  Both the lexical canonical path and the symlink-resolved
    real path must remain inside one of the configured roots, so neither
    ``..`` traversal nor symbolic links can escape the boundary.

    ``source`` values exposed to the resolver chain are canonical absolute
    paths stored as :class:`pathlib.Path` objects.
    """

    def __init__(self, roots):
        if isinstance(roots, (str, os.PathLike)):
            roots = (roots,)
        root_paths = []
        for root in roots:
            root_path = Path(root).expanduser().resolve(strict=True)
            if not root_path.is_dir():
                raise ValueError("include root is not a directory: %s"
                        % root_path)
            root_paths.append(root_path)
        if not root_paths:
            raise ValueError("FileIncludeResolver requires at least one root")
        self.roots = tuple(root_paths)

    def __call__(self, current_source, include_name):
        if current_source is None:
            base_dir = self.roots[0]
        else:
            # Canonicalise the current source through symlinks as well, so
            # a document reached via a link directory resolves further
            # relative references from its real location.
            current_path = Path(os.path.realpath(
                    Path(current_source).expanduser().absolute()))
            if not self._within_roots(current_path):
                raise IncludeError(
                        "current source %r is outside the include roots"
                        % str(current_source))
            base_dir = current_path.parent

        candidate = (base_dir / include_name).expanduser().absolute()
        canonical = Path(os.path.normpath(candidate))
        if not self._within_roots(canonical):
            raise IncludeError(
                    "include %r resolves outside the allowed roots"
                    % include_name)

        # Resolve symlinks as well; a link inside a root must not point out.
        real = Path(os.path.realpath(canonical))
        if not self._within_roots(real):
            raise IncludeError(
                    "include %r escapes the allowed roots via a symlink"
                    % include_name)
        if not real.is_file():
            raise IncludeError("included file does not exist: %s" % canonical)

        with open(real, 'r', encoding='utf-8') as stream:
            text = stream.read()
        return real, text

    def _within_roots(self, path):
        for root in self.roots:
            if path == root:
                return True
            try:
                path.relative_to(root)
            except ValueError:
                continue
            return True
        return False


def safe_load_include(stream, resolver, source=None,
        max_includes=DEFAULT_MAX_INCLUDES, max_depth=DEFAULT_MAX_DEPTH):
    """Parse the first YAML document, resolving ``!include`` tags safely."""
    loader = IncludeLoader(stream, resolver, source=source,
            max_includes=max_includes, max_depth=max_depth)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def safe_load_all_include(stream, resolver, source=None,
        max_includes=DEFAULT_MAX_INCLUDES, max_depth=DEFAULT_MAX_DEPTH):
    """Parse all YAML documents, resolving ``!include`` tags safely."""
    loader = IncludeLoader(stream, resolver, source=source,
            max_includes=max_includes, max_depth=max_depth)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()
