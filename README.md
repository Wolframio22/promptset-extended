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
- A Streamlit interface (`app.py`) in Spanish, English and Catalan to launch
  an analysis, browse the detected prompts with readable names for each
  heuristic, and review them one by one in their code: mark whether each
  detection is a prompt, rate it and comment it, then export the review.
- A test suite under `tests/` (see below).

See [`NOTICE`](NOTICE) for attribution to the original work and
[`README-original.md`](README-original.md) for the original PromptSet README.

## Setup

Use Python 3.10 or 3.11: tree-sitter 0.20 builds the grammar with
`distutils`, which Python 3.12 removed, so the last step below fails on
newer versions.

```bash
# Virtual environment and dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Build the Tree-sitter Python grammar (version 0.20.0 to match the pinned
# tree-sitter 0.20.4 in requirements.txt)
git clone --branch v0.20.0 https://github.com/tree-sitter/tree-sitter-python
mkdir -p build
SETUPTOOLS_USE_DISTUTILS=stdlib python -c "from tree_sitter import Language; Language.build_library('build/my-languages.so', ['tree-sitter-python'])"
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

Three steps, chosen at the top of the page:

1. **Analyse**: type GitHub repositories (`user/repo` is enough) or pick a
   local folder.
2. **Results**: summary charts, filters (repository, type of detection,
   review status, free text) and CSV export.
3. **Review**: each detection in its code, with a link to the exact line on
   GitHub. Mark whether it is a prompt, rate it (1–5 stars) and comment it.
   Reviews are saved in `data/revisiones.json` and included in the export,
   which can also be downloaded from this step.

The language (Spanish, English, Catalan) is chosen in the sidebar; the texts
live in `app_text.py`. To share the interface with other people (for example
through a tunnel), start it with `PROMPTSET_SOLO_GITHUB=1 streamlit run app.py`:
the option to analyse a folder of this computer is then hidden, and each
visitor's reviews stay in their own browser session.

`streamlit_app.py` starts the interface in that shared mode. It is the file
to choose when publishing it on [Streamlit Community Cloud](https://share.streamlit.io),
with Python 3.11 under *Advanced settings* (tree-sitter 0.20 compiles the
grammar with `distutils`, which Python 3.12 removed). `packages.txt` installs
the compiler and git there, and the first time the interface starts it
downloads and compiles the grammar.

## Studies

The `study/` folder holds the scripts of the large-scale study on GitHub
(RQ3): repository selection, an overnight run of both the original and the
extended heuristics, and the analysis that produces the tables and figures of
the thesis. See [`study/README.md`](study/README.md).

## Running the tests and the quality checks

```bash
pip install -r requirements-dev.txt
pytest                         # fast tests
pytest -m ""                   # all tests, including the long regression test
pytest -m "" --cov             # with coverage (engine, interface and texts)
ruff check .                   # linter (settings in ruff.toml)
```

GitHub Actions runs the linter and the whole test suite on every pull
request (`.github/workflows/ci.yml`).

## License

MIT for the code written for this thesis — see [LICENSE](LICENSE). The code
imported from PromptSet in the first commit came without a licence, so its
authors keep their rights; see [NOTICE](NOTICE).
