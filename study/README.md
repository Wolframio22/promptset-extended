# Studies of the thesis

Scripts that produce the data and figures of the empirical chapters. They use
the engine of this repository and do not change it.

```bash
source venv/bin/activate
pip install -r study/requirements.txt     # matplotlib, only for the figures
```

## RQ3: large-scale study on GitHub

*What are the characteristics of prompt-based repositories?* The study takes a
stratified random sample of public Python repositories tagged with
LLM-related topics, analyses each one with promptset-extended and with the
original PromptSet heuristics, and describes the libraries they use, how
many prompts they contain, how those prompts are written and how much the
two versions of the tool differ.

### 1. Select the repositories (about 6 minutes)

Needs a GitHub token, because the search API is used. Any personal token
works, no scopes are required (github.com → Settings → Developer settings →
Personal access tokens → Fine-grained token → Public repositories, read-only).

```bash
export GITHUB_TOKEN=github_pat_...        # or: gh auth login
python study/rq3/select_repos.py --out study/rq3 --size 1000
```

The query is `topic:<t> language:Python stars:<band> pushed:>=2025-01-01
archived:false fork:false` for 19 topics and four star bands (20–99, 100–499,
500–1999, 2000+). Curated lists (`awesome-*`), repositories over 500 MB and
the projects of the evaluation set are left out. The sample takes the same
number of repositories from each band, with a fixed seed.

Outputs: `candidates.csv` (every repository found), `sample.csv` (the
selected ones) and `selection.json` (parameters and date).

### 2. Run both engines (a few hours; can be left overnight)

```bash
python study/rq3/run_study.py --sample study/rq3/sample.csv --limit 3   # quick test
python study/rq3/run_study.py --sample study/rq3/sample.csv             # full run
```

The first run creates a git worktree with the original heuristics (commit
`6f7a749`) next to this checkout. Each repository is cloned with
`--depth 1`, analysed by both engines and deleted. The run can be stopped
with Ctrl+C and launched again: finished repositories are skipped. Results
go to `study/rq3/results/<owner>__<repo>/` (`meta.json`, `final.json`,
`original.json`). This folder is not tracked by git; zip it to share it.

### 3. Analyse

```bash
python study/rq3/analyze_study.py
```

Writes `study/rq3/analysis/`: `repos.csv`, `detections.csv`,
`heuristics.csv`, `summary.json`, `tables.tex` (LaTeX tables),
`figures/*.pdf|png` and `validation_sample.csv`.

Detections in test files are excluded with the same rule as in the
validation against the oracle (a `test`, `tests` or `testing` folder, or a
file named `test_*.py` or `*_test.py`).

### 4. Manual check of a random sample

`validation_sample.csv` holds about 180 detections drawn at random (seed 42)
from three groups: detections that both versions report, detections that
only the original reports (removed by the final version) and detections that
only the final version reports. Rows are shuffled so the group does not
influence the labelling. For each row, open the link and fill `es_prompt`:

- `si`: the captured fragment contains a prompt, or is the call that sends
  one to a language model;
- `no`: it is something else (a database query, a log message, a call that
  does not go to a model…);
- `dudoso`: it cannot be decided from the code.

Then run the analysis again with the labelled file:

```bash
python study/rq3/analyze_study.py --labels study/rq3/analysis/validation_sample.csv
```

The summary and `tables.tex` then include the share of real prompts in each
group (with a 95 % Wilson interval) and the estimated precision of each
version. The labelled file is never overwritten by later runs.
