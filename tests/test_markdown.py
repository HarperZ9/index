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


from index_graph.knowledge.markdown import render_markdown


def test_heading_levels():
    assert render_markdown("# A\n\n### B") == "<h1>A</h1>\n<h3>B</h3>"


def test_paragraph_joins_wrapped_lines_and_renders_inline():
    assert render_markdown("hello **world**\nsecond line") == "<p>hello <strong>world</strong> second line</p>"


def test_fenced_code_block_is_escaped_verbatim():
    md = "```\nif a < b: pass\n```"
    assert render_markdown(md) == "<pre><code>if a &lt; b: pass</code></pre>"


def test_unordered_list():
    assert render_markdown("- one\n- two") == "<ul>\n<li>one</li>\n<li>two</li>\n</ul>"


def test_ordered_list():
    assert render_markdown("1. one\n2. two") == "<ol>\n<li>one</li>\n<li>two</li>\n</ol>"


def test_task_list_items_render_checkboxes():
    out = render_markdown("- [ ] todo\n- [x] done")
    assert '<li class="task"><input type="checkbox" disabled> todo</li>' in out
    assert '<li class="task"><input type="checkbox" checked disabled> done</li>' in out


def test_blockquote():
    assert render_markdown("> quoted **b**") == "<blockquote>quoted <strong>b</strong></blockquote>"
