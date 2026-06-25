"""Per-ecosystem dependency resolvers."""
from .cpp import CppResolver
from .csharp import CSharpResolver
from .go import GoResolver
from .java import JavaResolver
from .javascript import JavaScriptResolver
from .php import PhpResolver
from .python import PythonResolver
from .ruby import RubyResolver
from .rust import RustResolver

ALL_RESOLVERS = (PythonResolver(), JavaScriptResolver(), RustResolver(), GoResolver(),
                 JavaResolver(), CSharpResolver(), RubyResolver(), PhpResolver(), CppResolver())
