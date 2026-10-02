import os
import stat

import pytest

import yaml
from yaml.include import (
    IncludeLoader,
    IncludeError,
    FileIncludeResolver,
    safe_load_include,
    safe_load_all_include,
)


class DictResolver:
    """In-memory resolver: maps source names to YAML text."""

    def __init__(self, documents, track=False):
        self.documents = documents
        self.calls = [] if track else None

    def __call__(self, current_source, include_name):
        if self.calls is not None:
            self.calls.append((current_source, include_name))
        if include_name not in self.documents:
            raise KeyError(include_name)
        return include_name, self.documents[include_name]


def test_in_memory_chain_a_b_c():
    documents = {
        'B': "value: !include C\n",
        'C': "inner: 42\n",
    }
    resolver = DictResolver(documents)
    result = safe_load_include("result: !include B\n", resolver, source='A')
    assert result == {'result': {'value': {'inner': 42}}}


def test_in_memory_cycle_a_b_a():
    documents = {
        'A': "x: !include B\n",
        'B': "back: !include A\n",
    }
    resolver = DictResolver(documents)
    with pytest.raises(IncludeError) as exc_info:
        safe_load_include("x: !include B\n", resolver, source='A')
    message = str(exc_info.value)
    assert 'circular !include' in message
    assert "'B'" in message and "'A'" in message
    # The include location chain connects both references.
    assert exc_info.value.frames[0][1] == 'B'
    assert exc_info.value.frames[1][1] == 'A'


def test_self_cycle_rejected():
    documents = {'S': "loop: !include S\n"}
    with pytest.raises(IncludeError, match='circular !include'):
        safe_load_include("x: !include S\n", DictResolver(documents),
                source='top')


def test_error_locations_chain_through_includes():
    # Document C contains a YAML syntax error; the resulting error must
    # report both include sites with line/column information.
    documents = {
        'B': "c: !include C\n",
        'C': "bad: [unclosed\n",
    }
    with pytest.raises(IncludeError) as exc_info:
        safe_load_include("b: !include B\n", DictResolver(documents),
                source='A')
    message = str(exc_info.value)
    assert "'B'" in message
    assert 'in "C"' in message
    assert 'line 1' in message
    outer = exc_info.value.frames[0]
    assert outer[0] == 'A' and outer[1] == 'B'
    assert outer[2].line == 0 and outer[2].column == 3
    inner = exc_info.value.frames[1]
    assert inner[0] == 'B' and inner[1] == 'C'
    assert inner[2].line == 0 and inner[2].column == 3


def test_duplicate_include_is_independent():
    documents = {'shared': "items: [1, 2, 3]\n"}
    text = "a: !include shared\nb: !include shared\n"
    result = safe_load_include(text, DictResolver(documents), source='root')
    assert result == {'a': {'items': [1, 2, 3]},
                      'b': {'items': [1, 2, 3]}}
    result['a']['items'].append(99)
    assert result['b']['items'] == [1, 2, 3]
    assert result['a']['items'] is not result['b']['items']


def test_duplicate_include_reuses_parsed_tree():
    documents = {'shared': "items: [1, 2, 3]\n"}
    resolver = DictResolver(documents, track=True)
    text = "a: !include shared\nb: !include shared\n"
    loader = IncludeLoader(text, resolver, source='root')
    try:
        loader.get_single_data()
        state = loader._include_state
    finally:
        loader.dispose()
    # Resolver consulted twice (once per tag), but the tree was parsed once.
    assert len(resolver.calls) == 2
    assert set(state.parsed) == {'shared'}


def test_separate_loads_share_no_state():
    documents = {'shared': "items: [1, 2, 3]\n"}
    resolver = DictResolver(documents)
    first = safe_load_include("x: !include shared\n", resolver, source='r1')
    second = safe_load_include("x: !include shared\n", resolver, source='r2')
    first['x']['items'].append(99)
    assert second['x']['items'] == [1, 2, 3]


def test_depth_limit():
    documents = {
        'f0': "x: 1\n",
        'f1': "d: !include f0\n",
        'f2': "d: !include f1\n",
    }
    # Chain root -> f2 -> f1 -> f0 is depth 3; max_depth=2 must reject it.
    with pytest.raises(IncludeError, match='depth limit'):
        safe_load_include("x: !include f2\n", DictResolver(documents),
                source='root', max_depth=2)
    result = safe_load_include("x: !include f2\n",
            DictResolver(documents), source='root', max_depth=3)
    assert result == {'x': {'d': {'d': {'x': 1}}}}


def test_total_include_limit():
    documents = {'s': "v: 1\n"}
    text = "\n".join("k%d: !include s" % i for i in range(5)) + "\n"
    with pytest.raises(IncludeError, match='too many !include'):
        safe_load_include(text, DictResolver(documents),
                source='root', max_includes=3)


def test_python_tags_remain_rejected():
    documents = {'evil': "!!python/object/apply:os.system ['echo pwned']\n"}
    with pytest.raises(IncludeError):
        safe_load_include("x: !include evil\n", DictResolver(documents),
                source='root')


def test_unknown_include_scalar_tag_style_rejected():
    with pytest.raises(IncludeError, match='scalar string'):
        safe_load_include("x: !include [a, b]\n", DictResolver({}),
                source='root')


def test_resolver_exception_is_wrapped_with_location():
    def boom(current_source, include_name):
        raise RuntimeError("storage unavailable")
    with pytest.raises(IncludeError) as exc_info:
        safe_load_include("x: !include missing\n", boom, source='root')
    message = str(exc_info.value)
    assert 'resolver failed' in message
    assert 'storage unavailable' in message
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert exc_info.value.frames[0][1] == 'missing'


def test_resolver_bad_return_value():
    def bad(current_source, include_name):
        return "only-a-source"
    with pytest.raises(IncludeError, match=r'\(source, text\)'):
        safe_load_include("x: !include x\n", bad, source='root')


def test_resolver_must_return_text_not_bytes():
    def bytes_resolver(current_source, include_name):
        return include_name, b"k: 1\n"
    with pytest.raises(IncludeError, match='YAML text as str'):
        safe_load_include("x: !include x\n", bytes_resolver, source='root')


def test_empty_include_becomes_none():
    result = safe_load_include("x: !include empty\n",
            DictResolver({'empty': ''}), source='root')
    assert result == {'x': None}


def test_multi_document_include_is_rejected_with_location():
    text = "---\na: 1\n---\nb: 2\n"
    with pytest.raises(IncludeError) as exc_info:
        safe_load_include("x: !include many\n",
                DictResolver({'many': text}), source='root')
    message = str(exc_info.value)
    assert 'expected a single document' in message
    assert "'many'" in message


def test_resolver_requires_source_argument_chain():
    seen = []

    def tracking(current_source, include_name):
        seen.append(current_source)
        return include_name, "k: 1\n"

    safe_load_include("a: !include B\n", tracking, source='A')
    assert seen == ['A']

    seen.clear()
    docs = {'B': "c: !include C\n", 'C': "k: 1\n"}

    def tracking2(current_source, include_name):
        seen.append(current_source)
        return include_name, docs[include_name]

    safe_load_include("b: !include B\n", tracking2, source='A')
    assert seen == ['A', 'B']


def test_include_list_and_scalar_content():
    documents = {
        'nums': "- 1\n- 2\n",
        'greeting': "hello\n",
    }
    result = safe_load_include(
            "numbers: !include nums\nsalute: !include greeting\n",
            DictResolver(documents), source='root')
    assert result == {'numbers': [1, 2], 'salute': 'hello'}


def test_safe_load_all_include_documents():
    documents = {'s': "v: 7\n"}
    stream = "---\nx: !include s\n---\ny: !include s\n"
    docs = list(safe_load_all_include(stream, DictResolver(documents),
            source='root'))
    assert docs == [{'x': {'v': 7}}, {'y': {'v': 7}}]
    docs[0]['x']['v'] = 999
    assert docs[1]['y']['v'] == 7


def test_loader_class_is_safe_loader():
    assert issubclass(IncludeLoader, yaml.SafeLoader)
    # Constructors of SafeLoader are inherited; only !include is added.
    assert '!include' in IncludeLoader.yaml_constructors


def test_file_resolver_relative_paths(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "shared.yaml").write_text("port: 8080\n")
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "service.yaml").write_text(
            "shared: !include ../common/shared.yaml\n")
    resolver = FileIncludeResolver(tmp_path)
    source = tmp_path / 'services' / 'service.yaml'
    with open(source) as stream:
        result = safe_load_include(stream, resolver)
    assert result == {'shared': {'port': 8080}}


def test_file_resolver_rejects_parent_traversal(tmp_path):
    outside = tmp_path / "secret.yaml"
    outside.write_text("secret: 1\n")
    root = tmp_path / "root"
    root.mkdir()
    (root / "main.yaml").write_text("s: !include ../secret.yaml\n")
    resolver = FileIncludeResolver(root)
    with open(root / 'main.yaml') as stream:
        with pytest.raises(IncludeError, match='outside the allowed roots'):
            safe_load_include(stream, resolver)


def test_file_resolver_rejects_absolute_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "secret.yaml"
    target.write_text("secret: 1\n")
    (root / "main.yaml").write_text(
            "s: !include %s\n" % target)
    resolver = FileIncludeResolver(root)
    with open(root / 'main.yaml') as stream:
        with pytest.raises(IncludeError, match='outside the allowed roots'):
            safe_load_include(stream, resolver)


def test_file_resolver_rejects_symlink_escape(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.yaml").write_text("secret: 1\n")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link.yaml").symlink_to(outside_dir / "secret.yaml")
    (root / "main.yaml").write_text("s: !include link.yaml\n")
    resolver = FileIncludeResolver(root)
    with open(root / 'main.yaml') as stream:
        with pytest.raises(IncludeError, match='symlink'):
            safe_load_include(stream, resolver)


def test_file_resolver_rejects_symlinked_directory_escape(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.yaml").write_text("secret: 1\n")
    root = tmp_path / "root"
    root.mkdir()
    (root / "ext").symlink_to(outside_dir, target_is_directory=True)
    (root / "main.yaml").write_text("s: !include ext/secret.yaml\n")
    resolver = FileIncludeResolver(root)
    with open(root / 'main.yaml') as stream:
        with pytest.raises(IncludeError, match='symlink'):
            safe_load_include(stream, resolver)


def test_file_resolver_multiple_roots(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_b / "piece.yaml").write_text("k: 5\n")
    (root_a / "main.yaml").write_text("p: !include %s\n"
            % (root_b / 'piece.yaml'))
    resolver = FileIncludeResolver([root_a, root_b])
    with open(root_a / 'main.yaml') as stream:
        result = safe_load_include(stream, resolver)
    assert result == {'p': {'k': 5}}


def test_file_resolver_chain_uses_relative_includes(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "c.yaml").write_text("deep: true\n")
    (tmp_path / "a" / "b.yaml").write_text("c: !include ../b/c.yaml\n")
    (tmp_path / "a" / "main.yaml").write_text("b: !include b.yaml\n")
    resolver = FileIncludeResolver(tmp_path)
    with open(tmp_path / 'a' / 'main.yaml') as stream:
        result = safe_load_include(stream, resolver)
    assert result == {'b': {'c': {'deep': True}}}


def test_file_resolver_missing_file(tmp_path):
    (tmp_path / "main.yaml").write_text("s: !include nope.yaml\n")
    resolver = FileIncludeResolver(tmp_path)
    with open(tmp_path / 'main.yaml') as stream:
        with pytest.raises(IncludeError, match='does not exist'):
            safe_load_include(stream, resolver)


def test_file_resolver_source_path_is_canonical(tmp_path):
    (tmp_path / "main.yaml").write_text(
            "s: !include sub/../shared.yaml\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "shared.yaml").write_text("ok: 1\n")
    resolver = FileIncludeResolver(tmp_path)
    with open(tmp_path / 'main.yaml') as stream:
        result = safe_load_include(stream, resolver)
    assert result == {'s': {'ok': 1}}
