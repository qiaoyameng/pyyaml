
__all__ = [
    'BaseDumper',
    'SafeDumper',
    'Dumper',
    'CoreSafeDumper',
    'CoreDumper',
]

from .emitter import *
from .serializer import *
from .representer import *
from .resolver import *

import datetime


VALID_SCALAR_SCHEMAS = ('core',)


def select_dumper_schema(dumper, schema=None):
    if schema is None:
        return
    if schema not in VALID_SCALAR_SCHEMAS:
        raise ValueError("unsupported scalar schema %r" % schema)
    dumper.yaml_implicit_resolvers = {
        key: values[:]
        for key, values in CoreResolver.yaml_implicit_resolvers.items()
    }
    dumper.yaml_path_resolvers = CoreResolver.yaml_path_resolvers.copy()
    dumper.yaml_representers = dumper.yaml_representers.copy()
    for data_type in (datetime.date, datetime.datetime):
        dumper.yaml_representers[data_type] = \
            CoreSafeRepresenter.yaml_representers[data_type]


def require_dumper_schema(schema):
    if schema is None:
        return 'core'
    if schema not in VALID_SCALAR_SCHEMAS:
        raise ValueError("unsupported scalar schema %r" % schema)
    return schema

class BaseDumper(Emitter, Serializer, BaseRepresenter, BaseResolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True, schema=None):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        Representer.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)
        select_dumper_schema(self, schema)

class SafeDumper(Emitter, Serializer, SafeRepresenter, Resolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True, schema=None):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        SafeRepresenter.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)
        select_dumper_schema(self, schema)

class Dumper(Emitter, Serializer, Representer, Resolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True, schema=None):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        Representer.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        Resolver.__init__(self)
        select_dumper_schema(self, schema)


class CoreSafeDumper(Emitter, Serializer, CoreSafeRepresenter, CoreResolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True, schema=None):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        CoreSafeRepresenter.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        CoreResolver.__init__(self)
        select_dumper_schema(self, require_dumper_schema(schema))


class CoreDumper(Emitter, Serializer, CoreRepresenter,
        CoreResolver):

    def __init__(self, stream,
            default_style=None, default_flow_style=False,
            canonical=None, indent=None, width=None,
            allow_unicode=None, line_break=None,
            encoding=None, explicit_start=None, explicit_end=None,
            version=None, tags=None, sort_keys=True, schema=None):
        Emitter.__init__(self, stream, canonical=canonical,
                indent=indent, width=width,
                allow_unicode=allow_unicode, line_break=line_break)
        Serializer.__init__(self, encoding=encoding,
                explicit_start=explicit_start, explicit_end=explicit_end,
                version=version, tags=tags)
        Representer.__init__(self, default_style=default_style,
                default_flow_style=default_flow_style, sort_keys=sort_keys)
        CoreResolver.__init__(self)
        select_dumper_schema(self, require_dumper_schema(schema))
