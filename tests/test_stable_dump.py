import pytest
import yaml


def make_documents():
    """Same content, different dict insertion orders, shared subobjects."""
    shared_list = [1, 'two', 2.5, None, True]
    shared_map = {'nested': shared_list, 'name': 'shared'}
    doc_a = {
        'zeta': shared_map,
        'alpha': shared_list,
        'middle': {'again': shared_map, 'list': shared_list},
        'floats': [float('inf'), float('-inf'), float('nan'), 1e17],
        'unicode': 'héllo',
    }
    doc_b = {
        'floats': [float('inf'), float('-inf'), float('nan'), 1e17],
        'middle': {'list': shared_list, 'again': shared_map},
        'unicode': 'héllo',
        'alpha': shared_list,
        'zeta': shared_map,
    }
    return doc_a, doc_b


def test_stable_dump_returns_bytes():
    data = yaml.stable_dump({'b': 1, 'a': [True, None, 2.5]})
    assert isinstance(data, bytes)
    assert data == b'a:\n- true\n- null\n- 2.5\nb: 1\n'


def test_insertion_order_does_not_matter():
    doc_a, doc_b = make_documents()
    assert yaml.stable_dump(doc_a) == yaml.stable_dump(doc_b)


def test_output_is_repeatable_across_calls():
    doc_a, _ = make_documents()
    assert yaml.stable_dump(doc_a) == yaml.stable_dump(doc_a)


def test_shared_subobjects_keep_identity_after_load():
    doc_a, _ = make_documents()
    data = yaml.stable_dump(doc_a)
    assert b'&id' in data and b'*id' in data
    back = yaml.safe_load(data)
    assert back['zeta'] is back['middle']['again']
    assert back['alpha'] is back['middle']['list']
    assert back['alpha'] is back['zeta']['nested']


def test_recursive_structure_is_repeatable():
    rec = []
    rec.append(rec)
    top = {'self': rec}
    data1 = yaml.stable_dump(top)
    data2 = yaml.stable_dump(top)
    assert data1 == data2
    back = yaml.safe_load(data1)
    assert back['self'][0] is back['self']


def test_anchor_names_do_not_depend_on_object_addresses():
    def build():
        shared = {'k': 'v'}
        return {'first': shared, 'second': shared}
    assert yaml.stable_dump(build()) == yaml.stable_dump(build())


def test_non_string_keys_are_rejected():
    for key in [1, 2.5, None, True, (1, 2), b'bytes']:
        with pytest.raises(yaml.representer.RepresenterError):
            yaml.stable_dump({key: 'value'})


def test_unsupported_types_are_rejected():
    import datetime
    for value in [object(), {1, 2}, datetime.date(2020, 1, 1),
                  datetime.datetime(2020, 1, 1), frozenset()]:
        with pytest.raises(yaml.representer.RepresenterError):
            yaml.stable_dump({'key': value})


def test_repr_of_rejected_object_is_never_called():
    class Explosive:
        def __repr__(self):
            raise AssertionError('repr() must not be called')
        __str__ = __repr__
    with pytest.raises(yaml.representer.RepresenterError):
        yaml.stable_dump({'key': Explosive()})
    with pytest.raises(yaml.representer.RepresenterError):
        yaml.stable_dump({Explosive(): 'value'})


def test_error_message_does_not_embed_the_object():
    class Sensitive:
        def __repr__(self):
            return 'SECRET-MARKER'
    try:
        yaml.stable_dump({'key': Sensitive()})
    except yaml.representer.RepresenterError as exc:
        assert 'SECRET-MARKER' not in str(exc)
    else:
        pytest.fail('expected RepresenterError')


def test_supported_scalars_and_special_floats():
    data = yaml.stable_dump({
        'none': None,
        'bool': True,
        'int': 42,
        'float': 0.5,
        'inf': float('inf'),
        'neg_inf': float('-inf'),
        'nan': float('nan'),
        'str': 'text',
        'bytes': b'\x00\x01',
        'tuple': (1, 2),
    })
    back = yaml.safe_load(data)
    assert back['none'] is None
    assert back['bool'] is True
    assert back['int'] == 42
    assert back['float'] == 0.5
    assert back['inf'] == float('inf')
    assert back['neg_inf'] == float('-inf')
    assert back['nan'] != back['nan']
    assert back['str'] == 'text'
    assert back['bytes'] == b'\x00\x01'
    assert back['tuple'] == [1, 2]
    assert b'.inf' in data and b'-.inf' in data and b'.nan' in data


def test_stable_dump_all_multiple_documents():
    data = yaml.stable_dump_all([{'a': 1}, {'b': 2}])
    docs = list(yaml.safe_load_all(data))
    assert docs == [{'a': 1}, {'b': 2}]


def test_stream_argument_receives_bytes():
    import io
    stream = io.BytesIO()
    result = yaml.stable_dump({'a': 1}, stream=stream)
    assert result is None
    assert stream.getvalue() == b'a: 1\n'


def test_regular_dump_is_unaffected():
    # The existing dump API keeps its formatting options and defaults.
    assert yaml.dump({'b': 1, 'a': 2}, sort_keys=False) == 'b: 1\na: 2\n'
    assert isinstance(yaml.safe_dump({'a': [1, 2]}), str)
