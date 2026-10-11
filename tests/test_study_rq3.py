"""Unit tests for the helpers of the RQ3 study scripts (study/rq3/)."""

import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")   # the analysis draws figures

STUDY = Path(__file__).resolve().parents[1] / "study" / "rq3"
sys.path.insert(0, str(STUDY))

import analyze_study as an  # noqa: E402
import run_study as rs  # noqa: E402


@pytest.mark.parametrize("path, expected", [
    ("tests/test_app.py", True),
    ("src/testing/helpers.py", True),
    ("pkg/test_utils.py", True),
    ("pkg/utils_test.py", True),
    ("src/contest/prompts.py", False),
    ("src/latest.py", False),
    ("prompts/system.py", False),
])
def test_test_files_follow_the_rq1_rule(path, expected):
    assert an.is_test_file(path) is expected


def test_features_of_a_literal_system_prompt():
    code = ('SYSTEM_PROMPT = """You are a careful reviewer.\n'
            '### Rules\n- Answer in JSON.\n- Think step by step."""')
    f = an.prompt_features(code)
    assert f["kind"] == "literal"
    assert (f["role"], f["json"], f["markdown"], f["multiline"], f["step"]) == (1, 1, 1, 1, 1)
    assert f["template"] == 0


def test_a_call_that_only_passes_a_variable_is_a_reference():
    f = an.prompt_features("client.chat.completions.create(model='gpt-4o', messages=messages)")
    assert f["kind"] == "referencia"
    assert f["chars"] == 0


@pytest.mark.parametrize("code, expected", [
    ('prompt = f"Summarise {text} in three short sentences"', 1),
    ('prompt = "Translate {source} into {target} for the user"', 1),
    ('prompt = "Hello {{ name }}, here is your daily summary"', 1),
    ('prompt = "Return the object as JSON like {\\"a\\": 1} and nothing more"', 0),
])
def test_template_detection(code, expected):
    assert an.prompt_features(code)["template"] == expected


def test_compare_marks_kept_added_and_removed():
    final = [{"file": "a.py", "heuristic": "h", "text": "x  = 1"},
             {"file": "a.py", "heuristic": "h", "text": "new"}]
    original = [{"file": "a.py", "heuristic": "h", "text": "x = 1"},
                {"file": "b.py", "heuristic": "h", "text": "old"}]
    an.compare(final, original)
    assert [r["status"] for r in final] == ["conservada", "nueva"]
    assert [r["status"] for r in original] == ["conservada", "eliminada"]


def test_compare_counts_repeated_detections_once_each():
    final = [{"file": "a.py", "heuristic": "h", "text": "p"}]
    original = [{"file": "a.py", "heuristic": "h", "text": "p"}] * 2
    an.compare(final, [dict(r) for r in original])
    assert final[0]["status"] == "conservada"


def test_wilson_interval():
    low, high = an.wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3)
    assert high == pytest.approx(0.7634, abs=1e-3)
    assert all(math.isnan(v) for v in an.wilson(0, 0))


def test_spearman_of_monotone_series():
    assert an.spearman([1, 2, 3, 4], [10, 20, 30, 400]) == pytest.approx(1.0)
    assert an.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_inventory_reads_imports_and_prompt_files(tmp_path):
    (tmp_path / "app.py").write_text("from google import genai\nimport openai as oa, os\n"
                                     "URL = 'https://api.openai.com/v1/chat/completions'\n")
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "system.j2").write_text("You are {{ role }}.")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "prompting.md").write_text("How to write prompts")
    (tmp_path / "demo.ipynb").write_text("{}")
    info = rs.inventory(tmp_path)
    assert info["libraries"] == ["Google Gemini", "OpenAI"]
    assert info["http_model_calls"] is True
    assert info["prompt_files_outside_py"] == 1          # docs/ is left out
    assert info["notebooks"] == 1
    assert info["py_files"] == 1 and info["py_loc"] == 3


def test_locate_line(tmp_path):
    source = tmp_path / "m.py"
    source.write_text("import os\n\nPROMPT = 'Say hi'\nPROMPT_2 = 'Bye'\n")
    assert rs.locate_line(source, "PROMPT = 'Say hi'") == 3
    assert rs.locate_line(source, "missing") is None
