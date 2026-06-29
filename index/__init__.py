from __future__ import annotations

import sys
from pathlib import Path

# Source-checkout bridge for the public CLI name. The packaged module remains
# index_graph; this only lets `python -m index` work from the repository root.
_src_root = Path(__file__).resolve().parents[1] / "src"
if _src_root.exists():
    sys.path.insert(0, str(_src_root))
