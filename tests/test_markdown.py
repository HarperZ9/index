from index_graph.knowledge.markdown import render_inline


def test_escapes_html_special_chars():
    assert render_inline("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_bold_and_italic():
    assert render_inline("**x** and *y*") == "<strong>x</strong> and <em>y</em>"


def test_inline_code_is_escaped_and_not_reparsed():
    assert render_inline("use `a < *b*`") == 'use <code>a &lt; *b*</code>'


def test_wikilink_becomes_atlas_target_span():
    out = render_inline("see [[Auth Design]]")
    assert '<a class="wikilink" href="#" data-atlas-target="auth-design">Auth Design</a>' in out


def test_wikilink_alias_renders_alias_text():
    out = render_inline("[[threat-model|the threats]]")
    assert 'data-atlas-target="threat-model"' in out
    assert ">the threats</a>" in out


def test_safe_link_kept_unsafe_dropped_to_text():
    assert '<a href="https://x.dev" rel="noopener noreferrer">site</a>' in render_inline("[site](https://x.dev)")
    assert render_inline("[x](javascript:alert(1))") == "x"  # unsafe scheme -> text only


def test_image_renders_alt_text_only_no_src():
    out = render_inline("![a diagram](https://evil/x.png)")
    assert out == '<span class="md-img">a diagram</span>'
    assert "evil" not in out and "http" not in out
