import pytest

import yaml


def test_memory_resolver_chain_and_independent_reuse():
    documents = {
        'A': "x: !include B\n",
        'B': "shared: !include C\nreuse: !include C\n",
        'C': "value: {nested: 1}\nitems: [1, 2]\n",
    }

    def resolver(source, name):
        return name, documents[name]

    data = yaml.safe_load_with_includes(
            documents['A'], resolver, source='A')

    assert data == {
        'x': {
            'shared': {'value': {'nested': 1}, 'items': [1, 2]},
            'reuse': {'value': {'nested': 1}, 'items': [1, 2]},
        },
    }

    shared = data['x']['shared']
    reused = data['x']['reuse']
    assert shared is not reused
    shared['value']['nested'] = 2
    shared['items'].append(3)
    assert reused == {'value': {'nested': 1}, 'items': [1, 2]}


def test_memory_resolver_detects_cycle():
    documents = {
        'A': "x: !include B\n",
        'B': "y: !include A\n",
    }

    def resolver(source, name):
        return name, documents[name]

    with pytest.raises(yaml.YAMLError) as exc_info:
        yaml.safe_load_with_includes(
                documents['A'], resolver, source='A')

    message = str(exc_info.value)
    assert "detected an include cycle" in message
    assert "'B' -> 'A'" in message
    assert '"A", line 1' in message
    assert '"B", line 1' in message


def test_errors_chain_include_location():
    documents = {
        'A': "x: !include B\n",
        'B': "y: !include C\n",
        'C': "z: {unclosed\n",
    }

    def resolver(source, name):
        return name, documents[name]

    with pytest.raises(yaml.YAMLError) as exc_info:
        yaml.safe_load_with_includes(
                documents['A'], resolver, source='A')

    message = str(exc_info.value)
    assert 'while including \'B\'' in message
    assert '"A", line 1' in message
    assert 'while including \'C\'' in message
    assert '"B", line 1' in message
    assert '"C", line 1' in message


def test_python_tags_remain_unsafe():
    text = "!!python/object/apply:os.system ['echo unsafe']\n"

    assert '!include' not in yaml.SafeLoader.yaml_constructors
    with pytest.raises(yaml.YAMLError):
        yaml.safe_load("x: !include B\n")

    with pytest.raises(yaml.YAMLError):
        yaml.safe_load_with_includes(
                text, lambda source, name: ('x', '{}'), source='root')


def test_file_resolver_relative_paths(tmp_path):
    root = tmp_path / 'root'
    nested = root / 'nested'
    nested.mkdir(parents=True)
    (root / 'a.yaml').write_text(
            "from_root: !include shared.yaml\n"
            "from_nested: !include nested/b.yaml\n", encoding='utf-8')
    (root / 'shared.yaml').write_text("answer: 1\n", encoding='utf-8')
    (nested / 'b.yaml').write_text(
            "local: !include c.yaml\nparent: !include ../shared.yaml\n",
            encoding='utf-8')
    (nested / 'c.yaml').write_text("answer: 2\n", encoding='utf-8')

    resolver = yaml.FileIncludeResolver(root)
    data = yaml.safe_load_with_includes(
            (root / 'a.yaml').read_text(encoding='utf-8'),
            resolver, source=str(root / 'a.yaml'))

    assert data == {
        'from_root': {'answer': 1},
        'from_nested': {
            'local': {'answer': 2},
            'parent': {'answer': 1},
        },
    }


def test_file_resolver_rejects_parent_directory(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside.yaml'
    outside.write_text("answer: 1\n", encoding='utf-8')
    source = root / 'a.yaml'
    source.write_text("x: !include ../outside.yaml\n", encoding='utf-8')

    with pytest.raises(yaml.IncludeBoundaryError):
        yaml.safe_load_with_includes(
                source.read_text(encoding='utf-8'),
                yaml.FileIncludeResolver(root), source=str(source))


def test_file_resolver_rejects_absolute_outside_path(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside.yaml'
    outside.write_text("answer: 1\n", encoding='utf-8')
    source = root / 'a.yaml'
    source.write_text("x: !include %s\n" % outside, encoding='utf-8')

    with pytest.raises(yaml.IncludeBoundaryError):
        yaml.safe_load_with_includes(
                source.read_text(encoding='utf-8'),
                yaml.FileIncludeResolver(root), source=str(source))


def test_file_resolver_rejects_symlink_escape(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    outside = tmp_path / 'outside.yaml'
    outside.write_text("answer: 1\n", encoding='utf-8')
    link = root / 'outside-link.yaml'
    link.symlink_to(outside)
    source = root / 'a.yaml'
    source.write_text("x: !include outside-link.yaml\n", encoding='utf-8')

    with pytest.raises(yaml.IncludeBoundaryError):
        yaml.safe_load_with_includes(
                source.read_text(encoding='utf-8'),
                yaml.FileIncludeResolver(root), source=str(source))


def test_file_resolver_allows_internal_symlink(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    target = root / 'target.yaml'
    target.write_text("answer: 1\n", encoding='utf-8')
    link = root / 'link.yaml'
    link.symlink_to(target)
    source = root / 'a.yaml'
    source.write_text("x: !include link.yaml\n", encoding='utf-8')

    data = yaml.safe_load_with_includes(
            source.read_text(encoding='utf-8'),
            yaml.FileIncludeResolver(root), source=str(source))

    assert data == {'x': {'answer': 1}}


def test_nested_file_resolver_boundary_error_keeps_type(tmp_path):
    root = tmp_path / 'root'
    nested = root / 'nested'
    nested.mkdir(parents=True)
    outside = tmp_path / 'outside.yaml'
    outside.write_text("answer: 1\n", encoding='utf-8')
    source = root / 'a.yaml'
    source.write_text("x: !include nested/b.yaml\n", encoding='utf-8')
    (nested / 'b.yaml').write_text(
            "y: !include ../../outside.yaml\n", encoding='utf-8')

    with pytest.raises(yaml.IncludeBoundaryError):
        yaml.safe_load_with_includes(
                source.read_text(encoding='utf-8'),
                yaml.FileIncludeResolver(root), source=str(source))


def test_limits_are_enforced():
    documents = {
        'A': "x: !include B\n",
        'B': "y: !include C\n",
        'C': "z: 1\n",
    }

    assert yaml.safe_load_with_includes(
            documents['A'],
            lambda source, name: (name, documents[name]),
            source='A', max_depth=2) == {'x': {'y': {'z': 1}}}

    with pytest.raises(yaml.YAMLError, match="maximum include depth"):
        yaml.safe_load_with_includes(
                documents['A'],
                lambda source, name: (name, documents[name]),
                source='A', max_depth=1)

    documents['B'] = "a: !include C\nb: !include C\n"
    with pytest.raises(yaml.YAMLError, match="too many includes"):
        yaml.safe_load_with_includes(
                documents['A'],
                lambda source, name: (name, documents[name]),
                source='A', max_includes=2)


def test_resolver_calls_reuse_parsed_source():
    calls = []
    documents = {
        'A': "first: !include B\nsecond: !include B\n",
        'B': "value: 1\n",
    }

    def resolver(source, name):
        calls.append((source, name))
        return name, documents[name]

    data = yaml.safe_load_with_includes(
            documents['A'], resolver, source='A')

    assert data == {
        'first': {'value': 1},
        'second': {'value': 1},
    }
    assert data['first'] is not data['second']
    assert calls == [('A', 'B'), ('A', 'B')]
