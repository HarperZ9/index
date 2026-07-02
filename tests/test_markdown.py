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


def test_pipe_table():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    out = render_markdown(md)
    assert "<table>" in out and "</table>" in out
    assert "<th>A</th>" in out and "<th>B</th>" in out
    assert "<td>1</td>" in out and "<td>2</td>" in out


def test_hostile_content_is_fully_escaped_no_breakout():
    md = "# <script>alert(1)</script>\n\n`</script>` and **<img src=x onerror=y>**"
    out = render_markdown(md)
    assert "<script>" not in out          # no raw opening tag survives
    assert "</script>" not in out         # no raw closing tag survives
    assert "&lt;script&gt;" in out
    assert "onerror" in out and "<img" not in out  # the literal text is kept, but escaped


def test_render_is_deterministic():
    md = "# T\n\n- a\n- b\n\n> q\n\n| x | y |\n| - | - |\n| 1 | 2 |"
    assert render_markdown(md) == render_markdown(md)


def test_literal_null_bytes_do_not_forge_a_code_sentinel():
    # a doc body with raw NUL + digits must not IndexError on the sentinel-restore step
    assert render_inline("x\x000\x00y") == "x0y"


def test_pipe_paragraph_that_is_not_a_table_terminates():
    # Regression: a paragraph whose FIRST line contains "|" without a table
    # separator beneath it used to loop forever (the paragraph branch never
    # consumed the line). It must render as a plain paragraph and terminate.
    md = "[a](x) | [b](y)\n\nnext para\n"
    out = render_markdown(md)
    assert out.count("<p>") == 2
    assert "next para" in out
    # the same shape mid-document, followed by a real table, keeps both
    md2 = "prose | with pipes\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
    out2 = render_markdown(md2)
    assert "prose | with pipes" in out2
    assert "<table>" in out2
