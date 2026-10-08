import re
from ast import literal_eval
import json
import os
from functools import lru_cache
from itertools import product
from tree_sitter import Language, Parser, Tree
from tqdm import tqdm
import uuid

if not os.path.exists("build/my-languages.so"):
    Language.build_library("build/my-languages.so", ["tree-sitter-python"])

PY_LANGUAGE = Language("build/my-languages.so", "python")


@lru_cache(maxsize=None)
def _query(source: str):
    """Compile a tree-sitter query once per process and reuse it.

    The heuristics used to compile their queries again for every file, which
    took most of the running time. The compiled query is immutable, so it can
    be shared by every call in the same worker process.
    """
    return PY_LANGUAGE.query(source)


# Parsers should be of type: Tree -> list[prompt_dict]
# prompt_dict should be a dictionary with a prompt key and a metadata key
def find_from_file(tree: Tree):
    results = []
    query = _query(
        """(call
            function: (attribute
                object: (identifier) @obj
                attribute: (identifier) @fn
            )
            arguments: (_) @args
            (#eq? @fn "from_file")
            (#match? @obj "Template")
        )"""
    )

    for capture, name in query.captures(tree.root_node):
        if name != "args":
            continue
        results.append(capture.text.decode("utf-8"))
    return results


def find_assignments(tree: Tree):
    rems: list[str] = []
    for aug, left_type, right_type in product(
        ["augmented_", ""],
        ["attribute", "identifier"],
        ["integer", "string", "binary_operator"],
    ):
        query = _query(
            f"""({aug}assignment
                left: ({left_type}) @var.name
                right: ({right_type}) @var.value
            ) @assign"""
        )
        for capture, name in query.captures(tree.root_node):
            if name == "assign":
                rems.append(capture.text.decode("utf-8"))
    return rems


def all_strings(tree: Tree):
    """All Strings heuristic"""
    result = []

    query = _query("((string) @var.value)")

    for usage in query.captures(tree.root_node):
        string = usage[0].text.decode("utf-8")
        if string.count(" ") > 2:
            result.append({"string": usage[0].text.decode("utf-8"), "metadata": {}})

    return result


def new_line_in_string(tree: Tree):
    """New Line in String definition heuristic"""
    result = []

    var_def_query = _query(
        """(expression_statement
            (assignment
                left: (identifier)
                right: (string) @var.value
            )
        )"""
    )

    for usage in var_def_query.captures(tree.root_node):
        # heuristic, check if string has a newline in it, if so then it's probably a prompt
        res = usage[0].text.decode("utf-8")
        if "\n" in res:
            result.append({"prompt": res, "metadata": {}})

    return result


# Variable-name vocabulary used by used_prompt_or_template_name, split in two
# tiers. "prompt" and "template" are strong signals on their own. The second
# tier covers names that the RQ1 error analysis found holding real prompts
# (BUG_FIX_QUERY, system_edit, AGENT_INSTRUCTIONS...), but which are also
# common in ordinary code: SQL queries, system paths, build instructions. For
# those, a longer literal is required before counting the assignment.
_STRONG_NAMES = ("prompt", "template")
_WEAK_NAMES = ("query", "system", "instruction")
_MIN_LEN_STRONG = 12
_MIN_LEN_WEAK = 40
_MIN_WORDS_WEAK = 6
# Share of prose words among all tokens. Measured on the evaluation set, real
# prompts held by ambiguous names scored between 0.66 and 1.00, while the
# database and tree-sitter queries that matched the same names scored 0.43 at
# most. The threshold sits between both groups.
_MIN_PROSE_RATIO = 0.5


# Prefix letters a Python string literal may carry right before its opening
# quote (f, r, b, u and their valid two-letter combinations).
_STRING_PREFIX_RE = re.compile(r"^[fFrRbBuU]{1,2}(?=[\"'])")

# Escaped whitespace (a backslash followed by n, t or r) left in the source
# text of an f-string.
_ESCAPED_WHITESPACE_RE = re.compile(r"\\[ntr]")


def _extract_string(text: str) -> str:
    """Return the content of a string literal, without prefix or quotes.

    literal_eval is tried first because it resolves escapes, raw strings and
    bytes exactly as Python would: an escaped "\\n" becomes a real line break,
    so the words on each side are counted separately. f-strings are rejected
    by literal_eval, so they fall back to stripping the prefix and the
    matching quotes by hand, which keeps placeholders such as {path} intact.

    A plain str.strip() is not enough: it removes the listed characters from
    both ends of the content too, so "buffer" would become "uffe".

    The result is only used to measure the text (its length and how much of
    it is prose), never as detection output, so the f-string fallback can
    afford to approximate: it turns escaped whitespace into real spaces so
    that words on either side of an escaped line break are counted
    separately. A full unicode_escape decode is avoided on purpose, since it
    mangles non-ASCII characters and prompts are not always written in
    English.
    """
    try:
        value = literal_eval(text)
        if isinstance(value, str):
            return value
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
    except (ValueError, SyntaxError):
        pass

    match = _STRING_PREFIX_RE.match(text)
    body = text[match.end():] if match else text
    for quote in ('"""', "'''", '"', "'"):
        if (len(body) >= 2 * len(quote)
                and body.startswith(quote) and body.endswith(quote)):
            body = body[len(quote):-len(quote)]
            break
    return _ESCAPED_WHITESPACE_RE.sub(" ", body)


def _longest_literal(node) -> str:
    """Longest string literal inside a subtree, quotes removed.

    The name query accepts any right-hand side, so it also matches token
    counters, empty lists, schema dictionaries and values pulled out of a
    structure at run time. Looking for an actual string literal separates
    the assignments that carry text from the rest.

    This is done after the capture rather than in the query itself:
    requiring right:(string) would also drop real prompts, because a literal
    followed by a chained call such as .strip() is no longer a string node.
    """
    longest = ""
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type == "string":
            text = _extract_string(
                current.text.decode("utf-8", errors="replace"))
            if len(text) > len(longest):
                longest = text
        pending.extend(current.children)
    return longest


def _natural_words(text: str) -> int:
    """Count tokens that read as ordinary prose words.

    A prompt is written in natural language; a tree-sitter query, a regular
    expression, a file path or a database query is not, even when it is
    long. Tokens carrying symbols, such as "(class_declaration)" or
    "source.node_id", are not counted. Neither are words written entirely in
    capitals: query languages such as SQL or Cypher spell their keywords
    that way (MATCH, WHERE, RETURN), whereas prose uses ordinary case.
    """
    count = 0
    for token in text.split():
        token = token.strip(".,:;!?\"'()")
        if len(token) >= 2 and token.isalpha() and not token.isupper():
            count += 1
    return count


def _prose_ratio(text: str) -> float:
    """Share of tokens that are prose words (see _natural_words)."""
    tokens = text.split()
    return _natural_words(text) / len(tokens) if tokens else 0.0


def _assigned_name(statement) -> str:
    """Name of the variable assigned in an expression_statement node."""
    for child in statement.named_children:
        left = child.child_by_field_name("left")
        if left is not None:
            return left.text.decode("utf-8", errors="replace").lower()
    return ""


def _carries_prompt_text(statement) -> bool:
    """Decide whether a name-matched assignment should count as a detection."""
    name = _assigned_name(statement)
    text = _longest_literal(statement)
    if any(word in name for word in _STRONG_NAMES):
        return len(text) >= _MIN_LEN_STRONG
    # Ambiguous names (query, system...) also appear as tree-sitter queries
    # or SQL, so require actual prose: many natural words and a high ratio.
    return (len(text) >= _MIN_LEN_WEAK
            and _natural_words(text) >= _MIN_WORDS_WEAK
            and _prose_ratio(text) >= _MIN_PROSE_RATIO)


def _case_insensitive(word: str) -> str:
    """Build a tree-sitter regex fragment matching a word in any case."""
    return "".join(f"[{c.upper()}{c.lower()}]" for c in word)


def used_prompt_or_template_name(tree: Tree):
    """Look for prompt-like names in assignments that actually assign text."""
    result = []
    pattern = "|".join(_case_insensitive(w) for w in _STRONG_NAMES + _WEAK_NAMES)

    query = _query(
        f"""(expression_statement
            (assignment
                left: (identifier) @var.name
                right: (_)
            )
            (#match? @var.name "({pattern})")
        ) @assign"""
    )
    query_2 = _query(
        f"""(expression_statement
            (augmented_assignment
                left: (identifier) @var.name
                right: (_)
            )
            (#match? @var.name "({pattern})")
        ) @assign"""
    )

    for usage, name in query.captures(tree.root_node):
        if name == "assign" and _carries_prompt_text(usage):
            result.append(usage.text.decode("utf-8"))

    for usage, name in query_2.captures(tree.root_node):
        if name == "assign" and _carries_prompt_text(usage):
            result.append(usage.text.decode("utf-8"))

    return result


def used_langchain_tool_class(tree: Tree):
    tool_query = _query(
        """(class_definition
            name: (identifier)
            superclasses: (argument_list
                (identifier) @superclass
            )
            (#match? @superclass "Tool")
            body: (block
                (expression_statement
                    (assignment
                        left: (identifier) @ident
                        right: (string) @string
                    )
                    (#eq? @ident "description")
                )
            )
        )"""
    )
    result = []
    for capture, name in tool_query.captures(tree.root_node):
        if name == "string":
            result.append(capture.text.decode("utf-8"))
    return result


def used_langchain_tool(tree: Tree):
    tool_query = _query(
        """(decorated_definition
        (decorator (identifier) @dec)
        definition: (function_definition
            name: (identifier)
            parameters: (_)
            return_type: (_)
            body: (block
                (expression_statement (string) @docstring))
        )
        (#eq? @dec "tool")
    )"""
    )
    result = []
    for capture, name in tool_query.captures(tree.root_node):
        if name == "docstring":
            result.append(capture.text.decode("utf-8"))
    return result


def used_in_langchain_llm_call(tree: Tree):
    """Find variables used in langchain llm calls"""
    result = []
    from_template_query = _query(
        """(call 
        function: 
        (attribute
            object: (identifier) @ob
            attribute: (identifier)
        )
        (#match? @ob "Template$")
        arguments: (argument_list)
    ) @call"""
    )

    template_query = _query(
        """(call 
        function: (identifier) @ob
        (#match? @ob "(Template|Message)$")
        arguments: (argument_list)
    ) @call"""
    )

    for capture in template_query.captures(tree.root_node):
        if capture[1] == "call":
            result.append(capture[0].text.decode("utf-8"))

    for capture in from_template_query.captures(tree.root_node):
        if capture[1] == "call":
            result.append(capture[0].text.decode("utf-8"))

    return result


def used_chat_function(tree: Tree):
    query = _query(
        """(call 
        function: 
        (attribute
            object: (identifier)
            attribute: (identifier) @fn
        )
        (#match? @fn "^(chat|summarize)$")
        arguments: (argument_list)
    ) @call"""
    )

    results = []
    for capture in query.captures(tree.root_node):
        if capture[1] == "call":
            results.append(capture[0].text.decode("utf-8"))
    return results


def used_in_openai_call(tree: Tree):
    """Find native openai library calls"""
    result = []

    call_query = _query(
        r"""(call
            function: (attribute) @fn.name
            arguments: (argument_list) @fn.args
            (#match? @fn.name "(\.[Cc]hat)?\.?[cC]ompletions?\.create")
        )"""
    )

    for usage in filter(
        lambda x: x[1] == "fn.args", call_query.captures(tree.root_node)
    ):
        result.append(usage[0].text.decode("utf-8"))

    return result


class PromptDetector:
    def __init__(self):
        self.parser = Parser()
        self.parser.set_language(PY_LANGUAGE)

        self.heuristics = []

    def add_heuristic(self, heuristic):
        self.heuristics.append(heuristic)

    def detect_prompts(self, filenames: list[str], run_id):
        results = {}

        for filename in tqdm(filenames):
            results |= self._detect_prompts(filename)

        with open(f"{run_id:03d}/prompts-{uuid.uuid4()}.json", "w") as w:
            json.dump(results, w)
    
    def _detect_prompts(self, filename: str):
        # Defensive reading: validate UTF-8 decodability before parsing.
        # Tree-sitter itself happily parses any byte sequence, but some
        # heuristics later call .text.decode("utf-8") on captured nodes;
        # a non-UTF-8 input then triggers SystemError inside the C
        # binding, which aborts the entire batch under multiprocessing.
        try:
            with open(filename, "rb") as f:
                raw = f.read()
            raw.decode("utf-8")  # validate
        except (UnicodeDecodeError, OSError) as e:
            print(f"[skip] {filename}: {type(e).__name__}")
            return {}

        tree = self.parser.parse(raw)

        results = {}
        for heuristic in self.heuristics:
            # A single misbehaving heuristic on one file must not abort
            # the rest of the batch. Record an empty result and continue.
            try:
                results[heuristic.__name__] = heuristic(tree)
            except Exception as e:
                print(f"[error] {heuristic.__name__} on {filename}: {type(e).__name__}: {e}")
                results[heuristic.__name__] = []
        try:
            results["variables"] = find_assignments(tree)
        except Exception as e:
            print(f"[error] find_assignments on {filename}: {type(e).__name__}: {e}")
            results["variables"] = []

        return {filename: results}
