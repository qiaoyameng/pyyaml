import pytest

import yaml


CONFIG = """\
defaults: &def
  retries: 3
  timeout: 30
service_a:
  <<: *def
  timeout: 60
service_b: *def
"""


def text_at(source, position):
    line = source.splitlines()[position.line - 1]
    return line[position.column - 1:]


def test_final_field_sources():
    data, index = yaml.safe_load_with_index(CONFIG)

    assert data == {
            'defaults': {'retries': 3, 'timeout': 30},
            'service_a': {'retries': 3, 'timeout': 60},
            'service_b': {'retries': 3, 'timeout': 30}}

    # The local override keeps its own position.
    timeout = index.entry(('service_a', 'timeout'))
    assert timeout.origin == 'definition'
    assert timeout.kind == 'scalar'
    assert text_at(CONFIG, timeout.start).startswith('60')
    assert text_at(CONFIG, timeout.key_start).startswith('timeout')

    # The merged field points back to the anchor definition ...
    retries = index.entry(('service_a', 'retries'))
    assert retries.origin == 'merge'
    assert retries.target == ('defaults', 'retries')
    assert text_at(CONFIG, retries.start).startswith('3')
    assert text_at(CONFIG, retries.key_start).startswith('retries')
    # ... and records where the merge happened.
    assert text_at(CONFIG, retries.usage).startswith('*def')

    # The second use of the anchor is a plain alias reference.
    alias = index.entry(('service_b',))
    assert alias.origin == 'alias'
    assert alias.target == ('defaults',)
    assert text_at(CONFIG, alias.usage).startswith('*def')

    # Resolution follows references to the definition.
    defined = index.resolve(('service_a', 'retries'))
    assert defined is index.entry(('defaults', 'retries'))
    assert defined.origin == 'definition'
    assert text_at(CONFIG, defined.start).startswith('3')
    assert index.resolve(('service_a', 'timeout')) is timeout
    through_alias = index.resolve(('service_b', 'timeout'))
    assert through_alias is index.entry(('defaults', 'timeout'))
    assert text_at(CONFIG, through_alias.start).startswith('30')


def test_object_identity_matches_safe_load():
    data, index = yaml.safe_load_with_index(CONFIG)
    plain = yaml.safe_load(CONFIG)

    assert data == plain
    # The shared anchor is a single shared object in both loaders.
    assert data['service_b'] is data['defaults']
    assert plain['service_b'] is plain['defaults']
    # A merge produces a new mapping in both loaders.
    assert data['service_a'] is not data['defaults']
    assert plain['service_a'] is not plain['defaults']


def test_paths_distinguish_string_keys_and_indices():
    source = '"0": zero\nitems:\n  - a\n  - b\n'
    data, index = yaml.safe_load_with_index(source)

    assert data == {'0': 'zero', 'items': ['a', 'b']}
    assert index.entry(('0',)).kind == 'scalar'
    assert text_at(source, index.entry(('0',)).start).startswith('zero')
    assert index.entry(('items', 0)).start.line == 3
    assert index.entry(('items', 1)).start.line == 4
    assert index.entry(('items', '0')) is None
    assert index.entry((0,)) is None


def test_recursive_alias_stays_finite():
    source = 'a: &x\n  - 1\n  - *x\n'
    data, index = yaml.safe_load_with_index(source)
    plain = yaml.safe_load(source)

    assert data['a'][1] is data['a']
    assert plain['a'][1] is plain['a']

    alias = index.entry(('a', 1))
    assert alias.origin == 'alias'
    assert alias.target == ('a',)
    assert text_at(source, alias.usage).startswith('*x')
    # Resolving through the recursive reference terminates.
    assert index.resolve(('a', 1)) is index.entry(('a',))
    assert index.resolve(('a', 1, 1, 0)) is index.entry(('a', 0))


def test_multiple_documents_are_numbered():
    source = '---\na: 1\n---\nb: 2\n'
    documents, index = yaml.safe_load_all_with_index(source)

    assert documents == [{'a': 1}, {'b': 2}]
    assert index.document_count == 2
    first = index.entry(('a',), document=0)
    second = index.entry(('b',), document=1)
    assert first.document == 0
    assert first.start.line == 2
    assert second.document == 1
    assert second.start.line == 4
    assert index.entry(('b',), document=0) is None


def test_merge_sequence_and_nested_merge():
    source = (
            'base: &base\n'
            '  x: 1\n'
            '  y: 2\n'
            'extra: &extra\n'
            '  y: 20\n'
            '  z: 30\n'
            'combined:\n'
            '  <<: [*extra, *base]\n'
            '  w: 0\n')
    data, index = yaml.safe_load_with_index(source)

    assert data['combined'] == {'x': 1, 'y': 20, 'z': 30, 'w': 0}
    # Earlier merge sources win.
    y = index.entry(('combined', 'y'))
    assert y.origin == 'merge'
    assert y.target == ('extra', 'y')
    assert text_at(source, y.start).startswith('20')
    x = index.entry(('combined', 'x'))
    assert x.origin == 'merge'
    assert x.target == ('base', 'x')
    assert text_at(source, x.usage).startswith('*base')
    assert index.resolve(('combined', 'z')) is index.entry(('extra', 'z'))
