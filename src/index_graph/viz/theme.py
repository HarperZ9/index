"""Project Telos palette + font tokens, shared by every renderer."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    bg: str = "#f4f3ef"
    ink: str = "#0b0c0e"
    accent: str = "#4636e8"
    teal: str = "#585c64"
    gold: str = "#0b0c0e"
    ok: str = "#2f3238"
    muted: str = "#585c64"
    alert: str = "#d9544d"
    hairline: str = "rgba(11,12,14,.14)"
    font_body: str = "Arial,Helvetica,sans-serif"
    font_mono: str = "ui-monospace,SFMono-Regular,Consolas,monospace"


THEME = Theme()

# role -> fill colour (deterministic mapping; unknown roles fall back to muted)
ROLE_COLOR = {
    "entrypoint": THEME.accent,
    "orchestrator": THEME.gold,
    "hub": THEME.ok,
    "library": THEME.teal,
    "leaf": THEME.muted,
    "isolated": THEME.muted,
    "external": THEME.hairline,
}


def css_variables() -> str:
    t = THEME
    return (
        ":root{"
        f"--bg:{t.bg};--ink:{t.ink};--accent:{t.accent};--teal:{t.teal};"
        f"--gold:{t.gold};--ok:{t.ok};--muted:{t.muted};--hairline:{t.hairline};"
        f"--font-body:{t.font_body};--font-mono:{t.font_mono};"
        "}"
    )


def svg_style() -> str:
    t = THEME
    roles = "".join(
        f".role-{role} rect{{fill:{color};}}" for role, color in ROLE_COLOR.items()
    )
    return (
        f"svg{{background-color:{t.bg};}}"
        f"text{{font-family:{t.font_mono};fill:{t.ink};}} /* labels are identifiers, use monospace not font-body */"
        f"rect{{stroke:{t.hairline};}}"
        f"{roles}"
        f".edge{{fill:none;stroke:{t.muted};}}"
        f".edge-high{{stroke:{t.ok};}}"
        f".edge-moderate{{stroke:{t.gold};stroke-dasharray:5 3;}}"
        f".edge-low{{stroke:{t.muted};stroke-dasharray:2 3;}}"
        f".edge-external{{stroke:{t.hairline};}}"
        f".edge-back{{stroke:{t.accent};}}"
        f".edge-cycle{{stroke:{t.alert};stroke-width:2.4;stroke-dasharray:none;}}"
        f".node.cycle rect{{stroke:{t.alert};stroke-width:2.4;}}"
    )
