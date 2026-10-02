
__all__ = ['BaseDumper', 'SafeDumper', 'Dumper', 'StableDumper']

from .emitter import *
from .serializer import *
from .representer import *
from .resolver import *

class BaseDumper(Emitter, Serializer, BaseRepresenter, BaseResolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        Representer.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)

class SafeDumper(Emitter, Serializer, SafeRepresenter, Resolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        SafeRepresenter.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)

class Dumper(Emitter, Serializer, Representer, Resolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        Representer.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)

class StableDumper(Emitter, Serializer, StableRepresenter, Resolver):
    """A dumper producing stable (deterministic) YAML bytes.

    All formatting options are fixed so that equal input data always
    yields byte-identical output, regardless of dict insertion order or
    object identities:

    - mapping keys are sorted (keys must be strings, so the order is
      total and platform independent),
    - block style, 2-space indent, ``\\n`` line breaks, UTF-8 encoding
      with unicode characters emitted verbatim,
    - float special values use the YAML forms ``.nan``/``.inf``/``-.inf``,
    - anchors for shared or recursive containers are named ``idNNN`` in
      document traversal order, never from object addresses.

    The stream must accept ``bytes``.
    """

    def __init__(self, stream):
        Emitter.__init__(self, stream, canonical=False,
                indent=2, width=80,
                allow_unicode=True, line_break='\n')
        Serializer.__init__(self, encoding='utf-8',
                explicit_start=False, explicit_end=False,
                version=None, tags=None)
        StableRepresenter.__init__(self, default_style=None,
                default_flow_style=False, sort_keys=True)
        Resolver.__init__(self)
