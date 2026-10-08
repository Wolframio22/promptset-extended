# Promptset-Extended

> Bachelor's Thesis (TFG) — Facultat d'Informàtica de Barcelona, UPC, 2025-2026.

Tool for automatically extracting LLM prompts from open-source Python
repositories. It is built on top of the original
[PromptSet](https://github.com/pisterlabs/promptset) extraction code, which is
preserved under `gen_prompts/` and extended for this thesis with:

- A static-analysis engine (`gen_prompts/find_prompts.py`) that scans a local
  folder, keeps only Python source files and skips dependency, cache and
  embedded-project directories.
- Seven detection heuristics over the Tree-sitter syntax tree
  (`gen_prompts/parsers.py`): OpenAI calls, LangChain calls, tool and tool-class
  declarations, a chat/summarize call, prompt/template variable names and
  templates loaded from a file.
- A JSON export and an optional CSV export (`--csv`) with one row per
  detection: repository, commit, file, line, heuristic and prompt text.
- A Streamlit interface (`app.py`) to launch an analysis and browse the
  detected prompts, jumping from each one to its place in the source.
- A test suite under `tests/` (see below).

See [`NOTICE`](NOTICE) for attribution to the original work and
[`README-original.md`](README-original.md) for the original PromptSet README.

## Setup

```bash
# Virtual environment and dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Build the Tree-sitter Python grammar (version 0.20.0 to match the pinned
# tree-sitter 0.20.4 in requirements.txt)
git clone --branch v0.20.0 https://github.com/tree-sitter/tree-sitter-python
mkdir -p build
python -c "from tree_sitter import Language; Language.build_library('build/my-languages.so', ['tree-sitter-python'])"
```

## Command-line usage

```bash
# Analyse a folder (a single repository, or a folder containing several).
python -m gen_prompts.find_prompts --run_id 1 --repo_dir ~/repos --threads 4

# Output: data/repo_data_export_001.json

# Add a CSV with repository, commit, file, line, heuristic and prompt:
python -m gen_prompts.find_prompts --run_id 1 --repo_dir ~/repos --threads 4 --csv

# Skip extra directories that hold copies of external projects:
python -m gen_prompts.find_prompts --run_id 1 --repo_dir ~/repos --exclude-dirs tests_data,examples
```

## Graphical interface

```bash
source venv/bin/activate
streamlit run app.py
```

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest            # fast tests
pytest -m slow    # the long-running regression test as well
```

## License

MIT — see [LICENSE](LICENSE).
