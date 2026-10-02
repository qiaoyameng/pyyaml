PyYAML
======

A full-featured YAML processing framework for Python

## Installation

To install, type `python setup.py install`.

By default, the `setup.py` script checks whether LibYAML is installed and if
so, builds and installs LibYAML bindings.
To skip the check and force installation of LibYAML bindings, use the option
`--with-libyaml`: `python setup.py --with-libyaml install`.
To disable the check and skip building and installing LibYAML bindings, use
`--without-libyaml`: `python setup.py --without-libyaml install`.

When LibYAML bindings are installed, you may use fast LibYAML-based parser and
emitter as follows:

    >>> yaml.load(stream, Loader=yaml.CLoader)
    >>> yaml.dump(data, Dumper=yaml.CDumper)

If you don't trust the input YAML stream, you should use:

    >>> yaml.safe_load(stream)

## Testing

PyYAML includes a comprehensive test suite.

To run the complete local test suite, type:

    make test

This creates a local Python environment, runs the pure Python tests, builds a
local copy of LibYAML, and then runs the LibYAML extension tests. The local
LibYAML build is pinned by `LIBYAML-REF`, which defaults to `0.2.5`.

To run only one test mode:

    make test-python
    make test-libyaml

To test with a specific Python version:

    make test PYTHON-VERSION=3.13.5

## Stable dump mode

`yaml.stable_dump(data)` serializes a document to deterministic UTF-8
bytes: equal input data always yields byte-identical output, regardless
of dict insertion order or object addresses. This makes the output
suitable for fingerprinting and hashing. All formatting options are
fixed (sorted string keys, block style, 2-space indent, `\n` line
breaks, UTF-8); the regular `yaml.dump` options are unaffected.

Only a restricted set of types is accepted; anything else raises
`yaml.representer.RepresenterError` immediately, without calling
`repr()` on the offending object:

    >>> yaml.stable_dump({'b': None, 'a': [1, 2.5, True, 'x', b'\x00']})
    b'a:\n- 1\n- 2.5\n- true\n- x\n- !!binary |\n  AA==\nb: null\n'
    >>> yaml.stable_dump({1: 'x'})          # non-string key
    RepresenterError: stable dump only accepts string mapping keys, ...
    >>> yaml.stable_dump({'d': datetime.date(2026, 1, 1)})
    RepresenterError: stable dump cannot represent objects of type 'date'

Supported: `None`, `bool`, `int`, `float` (special values are emitted
as `.nan`/`.inf`/`-.inf`), `str`, `bytes`, `list`/`tuple`, and `dict`
with string keys. Shared and recursive containers are emitted with
anchors named `idNNN` in traversal order, so their representation is
repeatable and loading the output restores the sharing:

    >>> shared = {'x': 1}
    >>> print(yaml.stable_dump({'a': shared, 'b': shared}).decode())
    a: &id001
      x: 1
    b: *id001

## Further Information

* For more information, check the
  [PyYAML homepage](https://github.com/yaml/pyyaml).

* [PyYAML tutorial and reference](http://pyyaml.org/wiki/PyYAMLDocumentation).

* Discuss PyYAML with the maintainers on
  Matrix at https://matrix.to/#/#pyyaml:yaml.io or
  IRC #pyyaml irc.libera.chat

* Submit bug reports and feature requests to the
  [PyYAML bug tracker](https://github.com/yaml/pyyaml/issues).

## License

The PyYAML module was written by Kirill Simonov <xi@resolvent.net>.
It is currently maintained by the YAML and Python communities.

PyYAML is released under the MIT license.

See the file LICENSE for more details.
