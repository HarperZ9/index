"""Per-ecosystem dependency resolvers."""
from .go import GoResolver
from .java import JavaResolver
from .javascript import JavaScriptResolver
from .python import PythonResolver
from .rust import RustResolver

ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver(), RustResolver(), GoResolver(), JavaResolver())
