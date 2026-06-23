"""Per-ecosystem dependency resolvers."""
from .javascript import JavaScriptResolver
from .python import PythonResolver

ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver())
