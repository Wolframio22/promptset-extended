# tfg-prompt-extractor

> Bachelor's Thesis (TFG) — Facultat d'Informàtica de Barcelona, UPC, 2025-2026.

Tool for automatically extracting LLM prompts from open-source Python
repositories. Built on top of the original
[PromptSet](https://github.com/pisterlabs/promptset) extraction code,
which is preserved unchanged under `gen_prompts/` and progressively
extended with:

- Batch processing from a list of repository URLs (no manual `git clone`)
- Checkpoint-based resumption of interrupted runs
- A Streamlit-based UI for exploration and manual evaluation
- Architectural refactor toward extensibility (Strategy Pattern for heuristics)
- Test suite, type checking, and CI

See [`NOTICE`](NOTICE) for attribution to the original work and
[`README-original.md`](README-original.md) for the original PromptSet README.

## Status

Active development. See `docs/` for the design and Sprint-by-Sprint
progress (coming in subsequent commits).

## Quick start (original PromptSet pipeline)

These are the commands to reproduce the original PromptSet extraction on
a downloaded repository, as inherited unchanged from the original work:

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install tree-sitter==0.20.4 black

# Build Tree-sitter Python grammar
git clone --branch v0.20.0 https://github.com/tree-sitter/tree-sitter-python
mkdir -p build
python -c "from tree_sitter import Language; Language.build_library('build/my-languages.so', ['tree-sitter-python'])"

# Run on a downloaded repository (example: Prometheus)
python -m gen_prompts.find_prompts --run_id 1 --repo_dir ~/git/Prometheus --threads 4
rm -rf data/black/    # clear cache between runs
python -m gen_prompts.reader --run_id 1

# Output: data/grouped-data-001-2.json
```

## License

MIT — see [LICENSE](LICENSE).
