import json
import os
import shutil
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
    new_line_in_string,
    find_from_file,
    all_strings,
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
    # detector.add_heuristic(new_line_in_string)
    # detector.add_heuristic(all_strings)

    detector.detect_prompts(filenames, run_id)


def batched(iterable, n):
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    it = iter(iterable)
    while batch := tuple(islice(it, n)):
        yield batch


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

    # Clean folder
    shutil.rmtree(f"{args.run_id:03d}")