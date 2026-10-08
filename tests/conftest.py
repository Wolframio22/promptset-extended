"""Shared fixtures for the promptset-extended test suite."""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# parsers.py loads the compiled grammar from a path relative to the working
# directory, so the suite must run from the repository root whatever
# directory pytest was launched from.
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from tree_sitter import Parser  # noqa: E402

from gen_prompts.parsers import PY_LANGUAGE  # noqa: E402


@pytest.fixture(scope="session")
def parse():
    """Return a function that turns Python source into a syntax tree."""
    parser = Parser()
    parser.set_language(PY_LANGUAGE)

    def _parse(source: str):
        return parser.parse(source.encode("utf-8"))

    return _parse
