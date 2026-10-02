import io

import pytest
import yaml


def build_config(key_order):
    shared = {'host': 'example.com', 'ports': [80, 443]}
    entries = {
        'name': 'demo',
        'debug': False,
        'ratio': 0.25,
        'limits': {'cpu': 2, 'mem': None},
        'primary': shared,
        'fallback': shared,
        'tags': ('a', 'b'),
    }
    return {key: entries[key] for key in key_order}


def test_stable_dump_is_insertion_order_independent():
    forward = build_config(['name', 'debug', 'ratio', 'limits',
                            'primary', 'fallback', 'tags'])
    reverse = build_config(['tags', 'fallback', 'primary', 'limits',
                            'ratio', 'debug', 'name'])
    assert yaml.stable_dump(forward) == yaml.stable_dump(reverse)
    assert isinstance(yaml.stable_dump(forward), bytes)


def test_stable_dump_sharing_roundtrip():
    data = build_config(['name', 'debug', 'ratio', 'limits',
                         'primary', 'fallback', 'tags'])
    out = yaml.stable_dump(data)
    assert b'&id001' in out and b'*id001' in out
    loaded = yaml.load(out, Loader=yaml.SafeLoader)
    assert loaded['primary'] is loaded['fallback']
    assert loaded['primary'] == {'host': 'example.com', 'ports': [80, 443]}


def test_stable_dump_recursive_reference():
    data = {'name': 'root'}
    data['self'] = data
    other = {'name': 'root'}
    other['self'] = other
    out = yaml.stable_dump(data)
    assert out == yaml.stable_dump(other)
    loaded = yaml.load(out, Loader=yaml.SafeLoader)
    assert loaded['self'] is loaded


def test_stable_dump_float_special_values():
    out = yaml.stable_dump({'nan': float('nan'), 'inf': float('inf'),
                            'ninf': float('-inf'), 'negzero': -0.0})
    assert out == yaml.stable_dump({'ninf': float('-inf'),
                                    'inf': float('inf'),
                                    'nan': float('nan'),
                                    'negzero': -0.0})
    assert b'.nan' in out and b'.inf' in out and b'-.inf' in out


def test_stable_dump_unicode_and_newlines():
    out = yaml.stable_dump({'text': 'héllo\nworld', 'emoji': '\U0001f600'})
    assert b'\r' not in out
    assert 'héllo'.encode('utf-8') in out


def test_stable_dump_rejects_non_string_keys():
    with pytest.raises(yaml.StableDumpError):
        yaml.stable_dump({1: 'one'})
    with pytest.raises(yaml.StableDumpError):
        yaml.stable_dump({('a', 'b'): 'tuple key'})
    with pytest.raises(yaml.StableDumpError):
        yaml.stable_dump({'ok': 1, 'nested': {'bad': {2: 3}}})


def test_stable_dump_rejects_unsupported_objects():
    class Custom:
        def __repr__(self):
            raise AssertionError('repr must not be called')

    for value in (object(), {1, 2}, b'bytes', Custom(), {'k': Custom()}):
        with pytest.raises(yaml.StableDumpError):
            yaml.stable_dump(value)


def test_stable_dump_error_mentions_type_name_only():
    class Secret:
        def __repr__(self):
            return 'SECRET-REPR'

    with pytest.raises(yaml.StableDumpError) as excinfo:
        yaml.stable_dump(Secret())
    assert 'Secret' in str(excinfo.value)
    assert 'SECRET-REPR' not in str(excinfo.value)


def test_stable_dump_rejects_subclass_instances():
    class MyStr(str):
        pass

    class MyDict(dict):
        pass

    with pytest.raises(yaml.StableDumpError):
        yaml.stable_dump(MyStr('x'))
    with pytest.raises(yaml.StableDumpError):
        yaml.stable_dump(MyDict(a=1))


def test_stable_dump_to_stream():
    stream = io.BytesIO()
    assert yaml.stable_dump({'a': 1}, stream) is None
    assert stream.getvalue() == yaml.stable_dump({'a': 1})


def test_regular_dump_options_unchanged():
    assert yaml.safe_dump({'b': 1, 'a': 2}) == 'a: 2\nb: 1\n'
    assert yaml.safe_dump({'b': 1, 'a': 2}, sort_keys=False) == 'b: 1\na: 2\n'
    assert yaml.dump({'a': [1, 2]}, default_flow_style=True) == '{a: [1, 2]}\n'
