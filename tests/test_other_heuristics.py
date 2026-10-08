"""Tests for the call-based and tool-based heuristics."""

import pytest

from gen_prompts.parsers import (
    find_from_file,
    used_chat_function,
    used_in_langchain_llm_call,
    used_in_openai_call,
    used_langchain_tool,
    used_langchain_tool_class,
)


class TestOpenAICall:
    @pytest.mark.parametrize("source", [
        'client.chat.completions.create(model="gpt-4", messages=msgs)',
        'openai.Completion.create(prompt="Say hello")',
    ])
    def test_detects_completion_calls(self, parse, source):
        assert len(used_in_openai_call(parse(source))) == 1

    def test_ignores_unrelated_calls(self, parse):
        assert used_in_openai_call(parse("client.files.create(path)")) == []


class TestLangchainCall:
    @pytest.mark.parametrize("source", [
        'HumanMessage(content="Hello there")',
        'SystemMessage(content="You are helpful.")',
        'PromptTemplate(template="Answer: {q}")',
        'ChatPromptTemplate.from_messages([("system", "Be brief.")])',
    ])
    def test_detects_message_and_template_constructors(self, parse, source):
        assert len(used_in_langchain_llm_call(parse(source))) >= 1

    def test_ignores_unrelated_constructors(self, parse):
        assert used_in_langchain_llm_call(parse("Counter(items)")) == []


class TestChatFunction:
    @pytest.mark.parametrize("source", ['model.chat("hi")', "llm.summarize(text)"])
    def test_detects_chat_and_summarize(self, parse, source):
        assert len(used_chat_function(parse(source))) == 1

    def test_requires_exact_method_name(self, parse):
        assert used_chat_function(parse("obj.chatter()")) == []


class TestLangchainTool:
    def test_detects_tool_docstring(self, parse):
        source = (
            "@tool\n"
            "def search(query: str) -> str:\n"
            '    """Search the codebase for relevant files."""\n'
            "    return run(query)\n"
        )
        assert len(used_langchain_tool(parse(source))) == 1

    @pytest.mark.xfail(
        reason="Known limitation: the query requires a return annotation, so "
               "tools declared without '-> type' are missed.",
        strict=True,
    )
    def test_detects_tool_without_return_annotation(self, parse):
        source = (
            "@tool\n"
            "def search(query: str):\n"
            '    """Search the codebase for relevant files."""\n'
            "    return run(query)\n"
        )
        assert len(used_langchain_tool(parse(source))) == 1


class TestLangchainToolClass:
    def test_detects_description_attribute(self, parse):
        source = (
            "class SearchTool(BaseTool):\n"
            '    name = "search"\n'
            '    description = "Search the codebase for relevant files."\n'
        )
        assert len(used_langchain_tool_class(parse(source))) == 1

    def test_ignores_classes_that_are_not_tools(self, parse):
        source = 'class Config(Base):\n    description = "Settings."\n'
        assert used_langchain_tool_class(parse(source)) == []


class TestFindFromFile:
    def test_detects_template_loaded_from_file(self, parse):
        source = 'PromptTemplate.from_file("prompts/repair.txt")'
        assert len(find_from_file(parse(source))) == 1

    def test_ignores_other_from_file_calls(self, parse):
        assert find_from_file(parse('Image.from_file("logo.png")')) == []
