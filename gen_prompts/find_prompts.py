import csv
import json
import os
import re
import shutil
import subprocess
from argparse import ArgumentParser
from glob import glob
from itertools import islice
from functools import partial
from multiprocessing import Pool
from gen_prompts.parsers import (
    PromptDetector,
    used_langchain_tool,
    used_chat_function,
    used_in_langchain_llm_call,
    used_in_openai_call,
    used_prompt_or_template_name,
    used_langchain_tool_class,
    find_from_file,
)


def process_chunk(filenames, run_id: int):
    detector = PromptDetector()
    detector.add_heuristic(used_langchain_tool_class)
    detector.add_heuristic(used_langchain_tool)
    detector.add_heuristic(used_in_langchain_llm_call)
    detector.add_heuristic(used_in_openai_call)
    detector.add_heuristic(used_chat_function)
    detector.add_heuristic(used_prompt_or_template_name)
    detector.add_heuristic(find_from_file)
    # The original new_line_in_string and all_strings heuristics are kept in
    # parsers.py for provenance but are intentionally not registered: they
    # flagged almost every string literal and produced too much noise.

    detector.detect_prompts(filenames, run_id)


def batched(iterable, n):
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    it = iter(iterable)
    while batch := tuple(islice(it, n)):
        yield batch


# ---------------------------------------------------------------------------
# Optional CSV export (RF4)
#
# The JSON export records, per file, the raw text captured by each heuristic.
# It does not record where in the file a prompt sits, nor which commit was
# analysed. The CSV export below adds that information so each row is
# self-contained and reproducible: repository, commit, file, line, heuristic
# and prompt text. The JSON output is left untouched, so existing scripts
# that read it keep working.
# ---------------------------------------------------------------------------

def _git_root(path: str):
    """Nearest ancestor directory that contains a .git folder, or None."""
    directory = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isdir(os.path.join(directory, ".git")):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _commit(root):
    """Current commit of a git repository, or '' if it cannot be read."""
    if root is None:
        return ""
    try:
        completed = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return completed.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


def _locate_line(path: str, fragment: str):
    """Line where a captured snippet starts, found by searching the file.

    The engine does not record positions, but each capture is a literal slice
    of the source, so searching for it recovers the line. The same approach is
    used by the graphical interface, so both agree on the reported line.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return ""
    needle = fragment.strip()
    # Avoid matching a longer identifier that merely starts with the snippet.
    pattern = re.escape(needle[:400]) + r"(?![A-Za-z0-9_])"
    found = re.search(pattern, content)
    if found is None:
        found = re.search(re.escape(needle[:120]), content)
    if found is None:
        return ""
    return content.count("\n", 0, found.start()) + 1


def export_csv(data: dict, repo_dir: str, csv_path: str) -> int:
    """Write one row per detection and return how many rows were written."""
    commits: dict = {}
    rows = []
    for filepath, heuristics in data.items():
        root = _git_root(filepath)
        if root not in commits:
            commits[root] = _commit(root)
        if root is not None:
            repository = os.path.basename(root)
            relative = os.path.relpath(filepath, root)
        else:
            relative = os.path.relpath(filepath, repo_dir)
            repository = relative.split(os.sep)[0]
        for heuristic, captures in heuristics.items():
            if heuristic == "variables" or not captures:
                continue
            for capture in captures:
                text = capture if isinstance(capture, str) else str(capture)
                rows.append({
                    "repository": repository,
                    "commit": commits[root],
                    "file": relative.replace(os.sep, "/"),
                    "line": _locate_line(filepath, text),
                    "heuristic": heuristic,
                    "prompt": " ".join(text.split()),
                })
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["repository", "commit", "file",
                           "line", "heuristic", "prompt"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    argparser = ArgumentParser()
    argparser.add_argument("--run_id", type=int, required=True)
    argparser.add_argument("--repo_dir", type=str, default="data/scraping-2.0/repos")
    argparser.add_argument("--threads", type=int, default=8)
    argparser.add_argument(
        "--exclude-dirs",
        dest="exclude_dirs",
        type=str,
        default="",
        help=(
            "Comma-separated directory names to skip, in addition to the "
            "built-in list. Useful for repositories that keep copies of "
            "external projects under their own directory names."
        ),
    )
    argparser.add_argument(
        "--csv",
        dest="csv",
        action="store_true",
        help=(
            "Also write data/repo_data_export_<run_id>.csv, with one row per "
            "detection (repository, commit, file, line, heuristic, prompt). "
            "The JSON output is written as well and is left unchanged."
        ),
    )
    args = argparser.parse_args()
    os.makedirs(f"{args.run_id:03d}", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Find all Python source files.
    #
    # The original implementation collected every file regardless of
    # extension, which caused parsers.py to feed binary blobs (images,
    # archives, compiled artefacts) into Tree-sitter. Once a heuristic
    # then tried to decode a captured node as UTF-8, the binding raised
    # SystemError and killed the whole batch.
    #
    # We also exclude directories holding code that is not the project under
    # study. These fall into two groups:
    #
    #   1. Dependency, environment and cache directories (venv,
    #      node_modules, ...). Their contents belong to other libraries.
    #
    #   2. Copies of unrelated projects. Some agent projects keep a whole
    #      set of external test projects inside their own tree. Measured on
    #      one repository of the study, those files were 5093 out of the
    #      5131 scanned, and 306 of them were reported as containing
    #      prompts even though none did. They belong to other projects and
    #      must not be attributed to the repository being analysed.
    #
    # The list below covers the directory names observed in this study.
    # Repositories that keep external code under a different name can be
    # handled with the --exclude-dirs option, without modifying the engine.
    EXCLUDED_DIRS = {
        # Dependencies, environments and caches
        ".git", ".venv", "venv", "env",
        "node_modules", "__pycache__", ".tox",
        ".mypy_cache", ".pytest_cache", ".ruff_cache",
        # Copies of unrelated projects kept inside the repository
        "testbed",
    }
    EXCLUDED_DIRS |= {
        d.strip() for d in args.exclude_dirs.split(",") if d.strip()
    }

    paths = []
    for root, dirs, files in os.walk(args.repo_dir):
        # Prune excluded dirs in-place so os.walk skips them entirely.
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if file.endswith(".py"):
                paths.append(os.path.join(root, file))

    print(f"[info] {len(paths)} Python files to analyse under {args.repo_dir}")

    # Batch into thread-count batches, and apply the heuristics
    # The original code had two undocumented limits: with a single
    # thread it silently discarded everything beyond 5000 files, and
    # with several it failed with 'n must be at least one' when the repository
    # had fewer files than threads.
    if args.threads == 1:
        process_chunk(paths, args.run_id)
    else:
        filenames_batched = batched(paths, max(1, len(paths) // args.threads))
        with Pool(args.threads) as p:
            p.map(partial(process_chunk, run_id=args.run_id), filenames_batched)

    # Join the thread data by loading output files
    data = {}
    for filename in glob(f"{args.run_id:03d}/prompts-*.json"):
        with open(filename) as f:
            data |= json.load(f)

    # save joined data
    with open(f"data/repo_data_export_{args.run_id:03d}.json", "w") as w:
        json.dump(data, w, indent=2, ensure_ascii=False)

    # Optional CSV export, enabled with --csv.
    if args.csv:
        csv_path = f"data/repo_data_export_{args.run_id:03d}.csv"
        n_rows = export_csv(data, args.repo_dir, csv_path)
        print(f"[info] {n_rows} detections written to {csv_path}")

    # Clean folder
    shutil.rmtree(f"{args.run_id:03d}")