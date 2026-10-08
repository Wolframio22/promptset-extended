"""Unit tests for the helpers that read and measure string literals."""

import pytest

from gen_prompts.parsers import (
    _case_insensitive,
    _extract_string,
    _natural_words,
    _prose_ratio,
)


class TestExtractString:
    @pytest.mark.parametrize("literal, expected", [
        ('"plain text"', "plain text"),
        ("'single quotes'", "single quotes"),
        ('"""triple quoted"""', "triple quoted"),
        ("'''triple single'''", "triple single"),
        ('r"raw \\d+ text"', "raw \\d+ text"),
        ('b"bytes here"', "bytes here"),
        ('rb"raw bytes"', "raw bytes"),
    ])
    def test_removes_prefix_and_quotes(self, literal, expected):
        assert _extract_string(literal) == expected

    def test_does_not_eat_letters_at_the_edges(self):
        # Regression: str.strip("\"'fFrRbB") turned "buffer" into "uffe".
        assert _extract_string('"buffer"') == "buffer"
        assert _extract_string('"before after"') == "before after"

    def test_resolves_escapes_in_plain_strings(self):
        assert _extract_string('"line one\\nline two"') == "line one\nline two"

    def test_keeps_placeholders_in_f_strings(self):
        assert _extract_string('f"Fix the bug in {path}"') == "Fix the bug in {path}"

    def test_turns_escaped_breaks_in_f_strings_into_spaces(self):
        text = _extract_string('f"first part.\\nsecond {x} part"')
        assert "\\n" not in text
        assert text.split() == ["first", "part.", "second", "{x}", "part"]

    def test_preserves_non_ascii_characters(self):
        # A full unicode_escape decode would mangle these.
        text = _extract_string('f"Revisa el código de {ruta} y explícalo.\\n"')
        assert "código" in text and "explícalo" in text


class TestNaturalWords:
    def test_counts_ordinary_prose(self):
        assert _natural_words("You are an expert assistant.") == 5

    def test_ignores_tokens_with_symbols(self):
        assert _natural_words("(class_declaration) @class source.node_id $id") == 0

    def test_ignores_all_caps_keywords(self):
        # Query languages spell keywords in capitals; prose does not.
        assert _natural_words("MATCH WHERE RETURN SELECT FROM") == 0

    def test_ignores_single_letters(self):
        assert _natural_words("a b c") == 0


class TestProseRatio:
    def test_prose_scores_high(self):
        assert _prose_ratio("Here is the bug report. Locate the faulty code.") == 1.0

    def test_cypher_scores_low(self):
        cypher = "MATCH (n:FileNode) WHERE n.node_id = $id RETURN n.text AS text"
        assert _prose_ratio(cypher) < 0.5

    def test_sql_scores_low(self):
        sql = "SELECT id, name, email FROM users WHERE active = 1 ORDER BY name DESC"
        assert _prose_ratio(sql) < 0.5

    def test_empty_text_scores_zero(self):
        assert _prose_ratio("") == 0.0


def test_case_insensitive_pattern():
    assert _case_insensitive("abc") == "[Aa][Bb][Cc]"
