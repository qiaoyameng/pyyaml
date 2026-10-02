
__all__ = [
    'BaseLoader',
    'FullLoader',
    'SafeLoader',
    'Loader',
    'UnsafeLoader',
    'CoreFullLoader',
    'CoreSafeLoader',
    'CoreLoader',
    'CoreUnsafeLoader',
]

from .reader import *
from .scanner import *
from .parser import *
from .composer import *
from .constructor import *
from .resolver import *


VALID_SCALAR_SCHEMAS = ('core',)


def select_loader_schema(loader, schema=None):
    if schema is None:
        return
    if schema not in VALID_SCALAR_SCHEMAS:
        raise ValueError("unsupported scalar schema %r" % schema)
    loader.yaml_implicit_resolvers = {
        key: values[:]
        for key, values in CoreResolver.yaml_implicit_resolvers.items()
    }
    loader.yaml_path_resolvers = CoreResolver.yaml_path_resolvers.copy()
    loader.yaml_constructors = loader.yaml_constructors.copy()
    core_constructors = {
        'tag:yaml.org,2002:null':
            CoreSafeConstructor.construct_yaml_null,
        'tag:yaml.org,2002:bool':
            CoreSafeConstructor.construct_yaml_bool,
        'tag:yaml.org,2002:int':
            CoreSafeConstructor.construct_yaml_int,
        'tag:yaml.org,2002:float':
            CoreSafeConstructor.construct_yaml_float,
        'tag:yaml.org,2002:timestamp':
            CoreSafeConstructor.construct_yaml_timestamp,
        'tag:yaml.org,2002:python/none':
            CoreSafeConstructor.construct_yaml_null,
        'tag:yaml.org,2002:python/bool':
            CoreSafeConstructor.construct_yaml_bool,
        'tag:yaml.org,2002:python/int':
            CoreSafeConstructor.construct_yaml_int,
        'tag:yaml.org,2002:python/float':
            CoreSafeConstructor.construct_yaml_float,
    }
    for tag, constructor in core_constructors.items():
        if tag in loader.yaml_constructors:
            loader.yaml_constructors[tag] = constructor


def require_loader_schema(schema):
    if schema is None:
        return 'core'
    if schema not in VALID_SCALAR_SCHEMAS:
        raise ValueError("unsupported scalar schema %r" % schema)
    return schema

class BaseLoader(Reader, Scanner, Parser, Composer, BaseConstructor, BaseResolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)
        select_loader_schema(self, schema)

class FullLoader(Reader, Scanner, Parser, Composer, FullConstructor, Resolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        FullConstructor.__init__(self)
        Resolver.__init__(self)
        select_loader_schema(self, schema)

class SafeLoader(Reader, Scanner, Parser, Composer, SafeConstructor, Resolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        SafeConstructor.__init__(self)
        Resolver.__init__(self)
        select_loader_schema(self, schema)

class Loader(Reader, Scanner, Parser, Composer, Constructor, Resolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        Constructor.__init__(self)
        Resolver.__init__(self)
        select_loader_schema(self, schema)

# UnsafeLoader is the same as Loader (which is and was always unsafe on
# untrusted input). Use of either Loader or UnsafeLoader should be rare, since
# FullLoad should be able to load almost all YAML safely. Loader is left intact
# to ensure backwards compatibility.
class UnsafeLoader(Reader, Scanner, Parser, Composer, Constructor, Resolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        Constructor.__init__(self)
        Resolver.__init__(self)
        select_loader_schema(self, schema)


class CoreFullLoader(Reader, Scanner, Parser, Composer, CoreFullConstructor,
        CoreResolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        CoreFullConstructor.__init__(self)
        CoreResolver.__init__(self)
        select_loader_schema(self, require_loader_schema(schema))


class CoreSafeLoader(Reader, Scanner, Parser, Composer, CoreSafeConstructor, CoreResolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        CoreSafeConstructor.__init__(self)
        CoreResolver.__init__(self)
        select_loader_schema(self, require_loader_schema(schema))


class CoreUnsafeLoader(Reader, Scanner, Parser, Composer,
        CoreUnsafeConstructor, CoreResolver):

    def __init__(self, stream, schema=None):
        Reader.__init__(self, stream)
        Scanner.__init__(self)
        Parser.__init__(self)
        Composer.__init__(self)
        CoreUnsafeConstructor.__init__(self)
        CoreResolver.__init__(self)
        select_loader_schema(self, require_loader_schema(schema))


class CoreLoader(CoreUnsafeLoader):
    pass
