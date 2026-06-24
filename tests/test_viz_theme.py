from index_graph.viz.theme import THEME, css_variables, svg_style


def test_theme_has_dark_serious_palette():
    assert THEME.bg == "#0d1b1c"
    assert THEME.accent == "#df5e00"
    assert THEME.ok == "#5fae93"
    # font stacks carry system fallbacks (no external font dependency)
    assert "serif" in THEME.font_body.lower()
    assert "monospace" in THEME.font_mono.lower()


def test_css_variables_is_a_root_block_with_every_token():
    css = css_variables()
    assert css.startswith(":root{")
    for token in ("--bg", "--ink", "--accent", "--teal", "--gold", "--ok", "--muted", "--hairline", "--font-body", "--font-mono"):
        assert token in css


def test_svg_style_references_palette_and_role_classes():
    style = svg_style()
    assert THEME.bg in style
    # one class per structural role + edge confidence classes
    for cls in (".role-entrypoint", ".role-orchestrator", ".role-hub", ".role-library", ".role-leaf", ".role-isolated", ".role-external", ".edge-high", ".edge-moderate", ".edge-low", ".edge-external", ".edge-back", "svg{"):
        assert cls in style


def test_theme_has_cycle_styles():
    from index_graph.viz.theme import svg_style, THEME
    s = svg_style()
    assert ".edge-cycle" in s
    assert THEME.alert  # cycle accent token present
