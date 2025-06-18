"""
Shared constants for the stub generator
"""

# Typing constructs that should be imported from typing module
TYPING_CONSTRUCTS = {
    'Dict', 'List', 'Set', 'Tuple', 'Optional', 'Union', 'Any', 'Type',
    'Callable', 'Iterable', 'Iterator', 'Sequence', 'Mapping', 'MutableMapping',
    'ClassVar', 'TypeVar', 'Generic', 'Literal', 'Final',
    'Annotated', 'Concatenate', 'ParamSpec', 'ForwardRef', 'NotRequired',
    'Required', 'TypedDict', 'NamedTuple', 'Counter', 'DefaultDict', 'OrderedDict'
}

# Built-in attributes that should be skipped during member processing
BUILTIN_ATTRS = {
    '__class__', '__doc__', '__module__', '__dict__', '__weakref__',
    '__abstractmethods__', '__abc_registry__', '__abc_cache__',
    '__abc_negative_cache__', '__abc_negative_cache_version__',
    '__subclasshook__', '__annotations__', '__orig_bases__',
    '__parameters__', '__origin__', '__args__'
}

# ABC internal attributes to skip
ABC_INTERNALS = {
    '_abc_impl', '_abc_registry', '_abc_cache', '_abc_negative_cache',
    '_abc_negative_cache_version', '_abc_positive_cache'
}

# Built-in modules that should be excluded from imports
BUILTIN_MODULES = {
    'abc', 'builtins', '__main__', 'typing', 'collections', 'collections.abc',
    'functools', 'itertools', 'operator', 'sys', 'os', 'pathlib', 're',
    'json', 'datetime', 'uuid', 'logging', 'threading', 'multiprocessing'
}

# Default directories to exclude from discovery
DEFAULT_EXCLUDE_DIRS = {
    '.git', '__pycache__', '.pytest_cache', 'node_modules',
    '.venv', 'venv', 'env', '.env', 'build', 'dist', 'tests'
}

# Methods that don't need return type annotations
VOID_METHODS = {
    '__init__', '__del__', '__enter__', '__exit__'
}

# Typing pattern for regex matching in signature text
TYPING_PATTERN = r'\b(' + '|'.join(TYPING_CONSTRUCTS) + r')\b'