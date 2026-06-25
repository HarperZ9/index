"""Per-ecosystem dependency resolvers."""
from .javascript import JavaScriptResolver
from .python import PythonResolver
from .rust import RustResolver

ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver(), RustResolver())
