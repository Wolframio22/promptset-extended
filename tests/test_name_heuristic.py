"""Tests for used_prompt_or_template_name, the variable-name heuristic.

The cases come from the RQ1 validation: each one reproduces a pattern that
was observed in the evaluation set, as a false positive, a false negative or
a correct detection.
"""

import re

import pytest

from gen_prompts.parsers import used_prompt_or_template_name


def detected_names(parse, source):
    """Names of the variables the heuristic reports in a piece of source."""
    found = used_prompt_or_template_name(parse(source))
    return {re.match(r"\s*(\w+)", capture).group(1) for capture in found}


class TestStrongNames:
    """'prompt' and 'template' only need an actual text literal."""

    @pytest.mark.parametrize("source", [
        'SYS_PROMPT = """You are an expert assistant for software issues."""',
        'prompt_template = "Analyse the following code: {code}"',
        'my_prompt = """\nDetailed instructions for the model.\n""".strip()',
        'experience_prompt = f"Based on case {case}, please retry the task."',
        'prompt = "First part of the instruction. " + "Second part."',
    ])
    def test_detects_assignments_holding_text(self, parse, source):
        assert len(detected_names(parse, source)) == 1

    @pytest.mark.parametrize("source", [
        "prompt_tokens = 5",
        "_re_pattern_templates = []",
        'prompt = request["messages"][0]["content"]',
        'tool_template = {"type": "function", "name": ""}',
        "prompt_messages = self.construct_prompt(idx)",
        "templates_path = ['_templates']",
    ])
    def test_rejects_assignments_without_prompt_text(self, parse, source):
        # All of these were false positives of the original heuristic.
        assert detected_names(parse, source) == set()

    def test_detects_augmented_assignment(self, parse):
        source = 'prompt += "Remember to answer only with the final patch."'
        assert detected_names(parse, source) == {"prompt"}


class TestWeakNames:
    """'query', 'system' and 'instruction' also need natural-language text."""

    @pytest.mark.parametrize("source", [
        'BUG_FIX_QUERY = """Here is the bug report. Locate the faulty code and propose a fix."""',
        'system_edit = """You are an editor agent. Apply the requested changes carefully."""',
        'AGENT_INSTRUCTIONS = """Follow these steps to reproduce the issue and then fix it."""',
        'THINKING_SYSTEM = """A user will ask you to solve a task. Draft your thinking first.""".strip()',
    ])
    def test_detects_prompts_with_ambiguous_names(self, parse, source):
        # All of these were false negatives of the original heuristic.
        assert len(detected_names(parse, source)) == 1

    @pytest.mark.parametrize("source", [
        # Cypher query, as found in Prometheus.
        'query = """UNWIND $edges AS edge MATCH (s:FileNode), (t:FileNode) '
        'WHERE s.node_id = edge.source CREATE (s) -[:HAS_FILE]-> (t)"""',
        # SQL query.
        'sql_query = "SELECT id, name, email FROM users WHERE active = 1 ORDER BY name"',
        # Tree-sitter query, as found in HyperAgent.
        'CHUNK_QUERY = """[ (class_declaration) @class (interface_declaration) @interface ]"""',
        # Ordinary code using the same words.
        "search_query = user_input.strip()",
        "system = platform.system()",
        'file_system = "/tmp/cache"',
        'build_instructions = "make all"',
    ])
    def test_rejects_queries_and_ordinary_code(self, parse, source):
        assert detected_names(parse, source) == set()


@pytest.mark.xfail(
    reason="Known limitation: a tree-sitter query made of plain node names "
           "reads as prose and passes the filter (observed in Lingxi).",
    strict=True,
)
def test_tree_sitter_query_with_plain_node_names(parse):
    source = ('query_func = PY_LANGUAGE.query("""name: (identifier) @name '
              'parameters: (parameters) @args body: (block) @block""")')
    assert detected_names(parse, source) == set()


@pytest.mark.xfail(
    reason="Known limitation: names outside the vocabulary are not covered "
           "(LOCALIZATION in swe-rl).",
    strict=True,
)
def test_prompt_with_name_outside_vocabulary(parse):
    source = 'LOCALIZATION = """Please look through the files and locate the bug."""'
    assert detected_names(parse, source) == {"LOCALIZATION"}
