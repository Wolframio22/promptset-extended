"""Run the RQ3 study: clone each sampled repository and analyse it twice.

For every repository in sample.csv the script
  1. makes a shallow clone (latest commit only),
  2. takes an inventory of the code: Python files and lines, LLM libraries
     imported, direct HTTP calls to model APIs, vector stores, notebooks and
     prompt files written in other formats,
  3. runs the detection engine of promptset-extended (this checkout) and the
     original PromptSet heuristics (commit 6f7a749, kept in a git worktree),
  4. stores the results under --out/<owner>__<repo>/ and deletes the clone.

Each engine's detections are saved as a list of records with the file, the
line where the capture starts, the heuristic and the captured text.

It can be stopped at any time and launched again: finished repositories are
skipped. A quick test before the full overnight run:

    python study/rq3/run_study.py --sample study/rq3/sample.csv --limit 3

Full run:

    python study/rq3/run_study.py --sample study/rq3/sample.csv
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # this checkout (final engine)
ORIGINAL_COMMIT = "6f7a749"                         # original heuristics, crash fixes only

# Same directory exclusions as the engine, so the inventory describes exactly
# the files that the heuristics analyse.
EXCLUDED_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".tox",
                 ".mypy_cache", ".pytest_cache", ".ruff_cache", "testbed"}

# Top-level modules mapped to the library they belong to.
LIBRARIES = {
    "openai": "OpenAI", "anthropic": "Anthropic",
    "langchain": "LangChain", "langchain_core": "LangChain", "langchain_openai": "LangChain",
    "langchain_community": "LangChain", "langchain_anthropic": "LangChain",
    "langchain_google_genai": "LangChain", "langchain_ollama": "LangChain",
    "langchain_text_splitters": "LangChain", "langgraph": "LangGraph",
    "llama_index": "LlamaIndex", "litellm": "LiteLLM",
    "google.generativeai": "Google Gemini", "google.genai": "Google Gemini",
    "vertexai": "Google Gemini",
    "transformers": "Hugging Face", "huggingface_hub": "Hugging Face",
    "ollama": "Ollama", "mistralai": "Mistral", "cohere": "Cohere", "groq": "Groq",
    "zhipuai": "Zhipu AI", "dashscope": "DashScope (Qwen)", "qianfan": "Qianfan (Baidu)",
    "together": "Together AI", "replicate": "Replicate",
    "vllm": "vLLM", "llama_cpp": "llama.cpp",
    "dspy": "DSPy", "autogen": "AutoGen", "autogen_agentchat": "AutoGen",
    "autogen_core": "AutoGen", "autogen_ext": "AutoGen",
    "crewai": "CrewAI", "haystack": "Haystack", "semantic_kernel": "Semantic Kernel",
    "instructor": "Instructor", "smolagents": "smolagents", "pydantic_ai": "PydanticAI",
    "guidance": "Guidance", "outlines": "Outlines", "mcp": "MCP", "fastmcp": "MCP",
}

# Vector stores and embedding indexes: a sign of retrieval (RAG) projects.
VECTOR_STORES = {
    "chromadb": "Chroma", "faiss": "FAISS", "pinecone": "Pinecone",
    "qdrant_client": "Qdrant", "weaviate": "Weaviate", "pymilvus": "Milvus",
    "lancedb": "LanceDB", "pgvector": "pgvector", "elasticsearch": "Elasticsearch",
}

# Model APIs called over plain HTTP, without an SDK.
HTTP_ENDPOINTS = re.compile(
    r"api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|"
    r"api\.deepseek\.com|api\.mistral\.ai|api\.groq\.com|openrouter\.ai/api|"
    r"dashscope\.aliyuncs\.com|open\.bigmodel\.cn|/v1/chat/completions|localhost:11434")

IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^\n#]+)", re.MULTILINE)
FROM_RE = re.compile(r"^[ \t]*from[ \t]+([A-Za-z_][\w.]*)[ \t]+import[ \t]+\(?([^\n#)]+)",
                     re.MULTILINE)

# Files in other formats that probably hold prompts: a prompt-like name or
# folder and a text format. Used only as a lower bound of prompts that a
# Python-only analysis cannot see.
PROMPT_FILE_EXT = {".yaml", ".yml", ".json", ".md", ".txt", ".jinja", ".jinja2", ".j2",
                   ".prompt", ".prompty", ".toml", ".mustache", ".hbs", ".tmpl", ".xml"}
# Documentation and tests often talk about prompts without holding any.
NOT_PROMPT_DIRS = {"docs", "doc", "documentation", "test", "tests", "testing"}
NOT_PROMPT_NAMES = ("readme", "changelog", "license", "contributing")


def is_prompt_file(path: Path, rel: str) -> bool:
    """A text file outside Python whose name or folder suggests it holds prompts."""
    if path.suffix.lower() not in PROMPT_FILE_EXT or "prompt" not in rel.lower():
        return False
    parts = [p.lower() for p in Path(rel).parts]
    if any(p in NOT_PROMPT_DIRS for p in parts[:-1]):
        return False
    return not parts[-1].startswith(NOT_PROMPT_NAMES)


def run(cmd, cwd=None, timeout=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_LFS_SKIP_SMUDGE="1")
    return subprocess.run(cmd, cwd=cwd, timeout=timeout, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, check=False)


def ensure_original_engine(path: Path) -> Path:
    """Create the worktree with the original heuristics the first time."""
    if not (path / "gen_prompts" / "parsers.py").exists():
        print(f"[setup] creating {path} at commit {ORIGINAL_COMMIT}")
        result = run(["git", "worktree", "add", "--detach", str(path), ORIGINAL_COMMIT], cwd=ROOT)
        if result.returncode != 0:
            sys.exit(f"Could not create the worktree:\n{result.stderr}")
    # The compiled grammar is not tracked by git: reuse the one of this checkout.
    so_file = ROOT / "build" / "my-languages.so"
    if not so_file.exists():
        sys.exit("Build the grammar first (see README): build/my-languages.so is missing.")
    (path / "build").mkdir(exist_ok=True)
    shutil.copy2(so_file, path / "build" / "my-languages.so")
    return path


def imported_modules(text: str):
    """Dotted names of every module imported by a Python source."""
    for match in IMPORT_RE.finditer(text):
        for part in match.group(1).split(","):
            name = part.strip().split(" as ")[0].strip()
            if name:
                yield name
    for match in FROM_RE.finditer(text):
        module = match.group(1)
        yield module
        # "from google import genai" names the package through the import list.
        for part in match.group(2).split(","):
            name = part.strip().split(" as ")[0].strip()
            if name.isidentifier():
                yield f"{module}.{name}"


def matches(module: str, table: dict):
    for key, label in table.items():
        if module == key or module.startswith(key + "."):
            yield label


def inventory(repo: Path) -> dict:
    """Describe the code of a repository, independently of the heuristics."""
    py_files = loc = notebooks = 0
    libraries, stores, prompt_files = set(), set(), []
    http_calls = False
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for name in files:
            path = Path(root) / name
            rel = path.relative_to(repo).as_posix()
            if name.endswith(".py"):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                py_files += 1
                loc += sum(1 for line in text.splitlines() if line.strip())
                for module in imported_modules(text):
                    libraries.update(matches(module, LIBRARIES))
                    stores.update(matches(module, VECTOR_STORES))
                if not http_calls and HTTP_ENDPOINTS.search(text):
                    http_calls = True
            elif name.endswith(".ipynb"):
                notebooks += 1
            elif is_prompt_file(path, rel):
                prompt_files.append(rel)
    return {"py_files": py_files, "py_loc": loc, "notebooks": notebooks,
            "libraries": sorted(libraries), "vector_stores": sorted(stores),
            "http_model_calls": http_calls,
            "prompt_files_outside_py": len(prompt_files),
            "prompt_files_examples": prompt_files[:20]}


def locate_line(path: Path, fragment: str):
    """Line where a captured snippet starts (same approach as the engine's CSV)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    needle = fragment.strip()
    found = re.search(re.escape(needle[:400]) + r"(?![A-Za-z0-9_])", content)
    if found is None:
        found = re.search(re.escape(needle[:120]), content)
    if found is None:
        return None
    return content.count("\n", 0, found.start()) + 1


def detect(engine: Path, repo: Path, run_id: int, threads: int, timeout: int):
    """Run find_prompts of one engine and return (records, seconds, error)."""
    cmd = [sys.executable, "-m", "gen_prompts.find_prompts", "--run_id", str(run_id),
           "--repo_dir", str(repo), "--threads", str(threads)]
    start = time.time()
    out_json = engine / "data" / f"repo_data_export_{run_id:03d}.json"
    try:
        result = run(cmd, cwd=engine, timeout=timeout)
    except subprocess.TimeoutExpired:
        shutil.rmtree(engine / f"{run_id:03d}", ignore_errors=True)
        out_json.unlink(missing_ok=True)
        return [], time.time() - start, "timeout"
    seconds = time.time() - start
    if result.returncode != 0 or not out_json.exists():
        return [], seconds, (result.stderr or "no output")[-2000:]
    data = json.loads(out_json.read_text(encoding="utf-8"))
    out_json.unlink()
    for leftover in (engine / "data").glob(f"repo_data_export_{run_id:03d}.*"):
        leftover.unlink()
    records = []
    for path, heuristics in data.items():
        rel = os.path.relpath(path, repo).replace(os.sep, "/")
        for heuristic, captures in heuristics.items():
            if heuristic in ("variables", "lines") or not captures:
                continue
            for capture in captures:
                text = capture if isinstance(capture, str) else str(capture)
                records.append({"file": rel, "line": locate_line(Path(path), text),
                                "heuristic": heuristic, "text": text})
    return records, seconds, ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", default="study/rq3/sample.csv")
    parser.add_argument("--out", default="study/rq3/results")
    parser.add_argument("--workdir", default="study/rq3/clones", help="temporary clones")
    parser.add_argument("--original-engine", default=str(ROOT.parent / "promptset-extended-original"))
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--clone-timeout", type=int, default=600)
    parser.add_argument("--engine-timeout", type=int, default=1800)
    parser.add_argument("--limit", type=int, default=0, help="stop after N repositories (test runs)")
    parser.add_argument("--keep-clones", action="store_true")
    args = parser.parse_args()

    original = ensure_original_engine(Path(args.original_engine).resolve())
    out, work = Path(args.out).resolve(), Path(args.workdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    with open(args.sample, newline="", encoding="utf-8") as f:
        sample = list(csv.DictReader(f))

    done_now = 0
    for i, repo_info in enumerate(sample, 1):
        slug = repo_info["full_name"].replace("/", "__")
        target = out / slug
        if (target / "done").exists():
            continue
        if args.limit and done_now >= args.limit:
            break
        target.mkdir(exist_ok=True)
        clone = work / slug
        shutil.rmtree(clone, ignore_errors=True)
        meta = dict(repo_info, slug=slug, error="")
        print(f"[{i}/{len(sample)}] {repo_info['full_name']}", flush=True)
        start = time.time()
        try:
            result = run(["git", "clone", "--depth", "1", "--single-branch", "--no-tags", "-q",
                          repo_info["url"], str(clone)], timeout=args.clone_timeout)
            ok = result.returncode == 0
            meta["error"] = "" if ok else ("clone failed: " + result.stderr[-500:])
        except subprocess.TimeoutExpired:
            ok, meta["error"] = False, "clone timeout"
        if ok:
            meta["commit"] = run(["git", "rev-parse", "HEAD"], cwd=clone).stdout.strip()
            meta.update(inventory(clone))
            for name, engine, rid in (("final", ROOT, 7000 + i), ("original", original, 8000 + i)):
                records, seconds, error = detect(engine, clone, rid, args.threads,
                                                 args.engine_timeout)
                (target / f"{name}.json").write_text(
                    json.dumps(records, ensure_ascii=False), encoding="utf-8")
                meta[f"{name}_seconds"] = round(seconds, 2)
                meta[f"{name}_files"] = len({r["file"] for r in records})
                meta[f"{name}_detections"] = len(records)
                if error:
                    meta["error"] += f" {name}: {error}"
        meta["total_seconds"] = round(time.time() - start, 1)
        (target / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False),
                                          encoding="utf-8")
        (target / "done").write_text("ok", encoding="utf-8")
        if not args.keep_clones:
            shutil.rmtree(clone, ignore_errors=True)
        done_now += 1
        print(f"    py={meta.get('py_files', 0)} final={meta.get('final_detections', 0)} "
              f"original={meta.get('original_detections', 0)} "
              f"{meta['total_seconds']} s {meta['error'][:80]}", flush=True)
    print("finished")


if __name__ == "__main__":
    main()
