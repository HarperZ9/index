import warnings
warnings.warn(
    "workspace-repo-map has been renamed to 'index-graph' (CLI: 'index'). "
    "Install it with: pip install index-graph",
    DeprecationWarning, stacklevel=2,
)
__version__ = "0.2.1"
