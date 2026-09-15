from context_fabric.enrichment.html_text import strip_html


def test_strip_html_removes_tags_and_decodes_entities():
    raw = "<p>Design for SSO &amp; OAuth. References <strong>PR-42</strong>.</p>"
    assert strip_html(raw) == "Design for SSO & OAuth. References PR-42 ."


def test_strip_html_drops_script_and_style_content_entirely():
    raw = "<style>.x{color:red}</style><p>Visible text</p><script>alert(1)</script>"
    text = strip_html(raw)
    assert text == "Visible text"


def test_strip_html_collapses_whitespace():
    raw = "<p>Line one.</p>\n\n\n<p>   Line   two.   </p>"
    assert strip_html(raw) == "Line one.\nLine two."


def test_strip_html_truncates_to_max_chars():
    raw = "<p>" + ("word " * 100) + "</p>"
    text = strip_html(raw, max_chars=20)
    assert len(text) == 20


def test_strip_html_empty_input_returns_empty_string():
    assert strip_html("") == ""
    assert strip_html(None) == ""  # type: ignore[arg-type]
