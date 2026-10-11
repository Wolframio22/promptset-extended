"""Select the repositories for the RQ3 study through the GitHub search API.

The sample targets public Python repositories that are tagged with
LLM-related topics, are still active and are not forks or archives. Search
results are capped at 1000 per query, so the pool is built from several
queries (one per topic and star band) and then a stratified random sample is
drawn, the same number of repositories from each star band, so that popular
and modest projects are equally represented.

Usage (needs a GitHub token, either in GITHUB_TOKEN or through the gh CLI):

    python study/rq3/select_repos.py --out study/rq3 --size 1000

Outputs, in the --out folder:
    candidates.csv   every repository returned by the queries (deduplicated)
    sample.csv       the selected repositories, input for run_study.py
    selection.json   parameters and date of the selection, for the thesis
"""

import argparse
import csv
import datetime as dt
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com/search/repositories"

# Topics that identify LLM-based projects. A repository qualifies if it
# carries at least one of them.
TOPICS = [
    "llm", "large-language-models", "langchain", "openai", "chatgpt", "gpt",
    "llm-agent", "llm-agents", "ai-agent", "ai-agents", "rag",
    "retrieval-augmented-generation", "anthropic", "claude", "llamaindex",
    "autogen", "prompt-engineering", "generative-ai", "llm-app",
]
# "agents" alone was left out on purpose: it also tags reinforcement-learning
# agents and game bots that have nothing to do with language models.

# Star bands used to stratify the sample.
BANDS = [("20..99", "20-99"), ("100..499", "100-499"),
         ("500..1999", "500-1999"), (">=2000", "2000+")]

# Projects of the evaluation set (Chapters 5 and 6). They are left out so
# that RQ3 does not reuse repositories whose prompts were studied by hand.
EXCLUDED = {
    "euniai/prometheus", "autocoderoversg/auto-code-rover", "openautocoder/agentless",
    "lingmatongyi/lingma-swe-gpt", "bytedance/trae-agent", "jd-opensource/joycode-agent",
    "nimasteryang/lingxi", "codefuse-ai/codefuse-cgm", "facebookresearch/swe-rl",
    "augmentcode/augment-swebench-agent", "sorendunn/agentless-lite",
    "ucsb-mlsec/co-patcher", "nl2code/coder", "darsagent/dars-agent",
    "experepair/experepair", "fsoft-ai4code/hyperagent", "gleam-lab/kgcompass",
    "mcts-refine/mcts-refine-codes", "fishmingyu/orcaloca", "evandiewald/aegis",
    "swe-agent/swe-agent", "swe-agent/mini-swe-agent", "agentscope-ai/agentscope",
    "lingmatongyi/anonymousswegpt", "internlm/swe-fixer",
}

FIELDS = ["full_name", "url", "stars", "forks", "size_kb", "created_at", "pushed_at",
          "default_branch", "license", "topics", "description", "band"]


def github_token() -> str:
    """Token from GITHUB_TOKEN, or from the gh CLI if it is logged in."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("A GitHub token is needed: export GITHUB_TOKEN=... or run 'gh auth login'.")


def search(query: str, page: int, token: str) -> dict:
    """One page of repository search results, waiting out the rate limit."""
    params = urllib.parse.urlencode({"q": query, "sort": "stars", "order": "desc",
                                     "per_page": 100, "page": page})
    request = urllib.request.Request(f"{API}?{params}", headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "promptset-extended-rq3",
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                sys.exit("GitHub rejected the token (401). Check GITHUB_TOKEN or 'gh auth login'.")
            if error.code in (403, 429):
                if error.headers.get("Retry-After"):
                    wait = int(error.headers["Retry-After"]) + 1
                else:
                    reset = int(error.headers.get("X-RateLimit-Reset", time.time() + 60))
                    wait = max(5, reset - int(time.time()) + 2)
                print(f"  rate limit reached, waiting {wait} s")
                time.sleep(wait)
                continue
            if error.code == 422:      # beyond the 1000-result window
                return {"items": []}
            raise
        except urllib.error.URLError:
            time.sleep(10 * (attempt + 1))
    return {"items": []}


def row_from_item(item: dict, band: str) -> dict:
    return {
        "full_name": item["full_name"],
        "url": item["html_url"],
        "stars": item["stargazers_count"],
        "forks": item["forks_count"],
        "size_kb": item["size"],
        "created_at": item["created_at"],
        "pushed_at": item["pushed_at"],
        "default_branch": item.get("default_branch", ""),
        "license": (item.get("license") or {}).get("spdx_id", ""),
        "topics": ";".join(item.get("topics", [])),
        "description": " ".join((item.get("description") or "").split())[:300],
        "band": band,
    }


def keep(row: dict, max_size_mb: int) -> bool:
    """Drop excluded projects, curated lists and very large repositories."""
    name = row["full_name"].lower()
    if name in EXCLUDED:
        return False
    if name.split("/")[1].startswith("awesome"):
        return False
    return row["size_kb"] <= max_size_mb * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="study/rq3")
    parser.add_argument("--size", type=int, default=1000, help="repositories in the sample")
    parser.add_argument("--pages", type=int, default=2, help="result pages per query (100 each)")
    parser.add_argument("--pushed-since", default="2025-01-01")
    parser.add_argument("--max-size-mb", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    token = github_token()
    os.makedirs(args.out, exist_ok=True)
    pool = {}
    queries = [(t, b) for t in TOPICS for b in BANDS]
    for i, (topic, (stars, band)) in enumerate(queries, 1):
        query = (f"topic:{topic} language:Python stars:{stars} "
                 f"pushed:>={args.pushed_since} archived:false fork:false")
        found = 0
        for page in range(1, args.pages + 1):
            items = search(query, page, token).get("items", [])
            for item in items:
                row = row_from_item(item, band)
                if keep(row, args.max_size_mb):
                    pool.setdefault(row["full_name"].lower(), row)
                    found += 1
            time.sleep(2.2)            # search API: 30 requests per minute
            if len(items) < 100:
                break
        print(f"[{i}/{len(queries)}] {topic:32s} {band:9s} -> {found:4d}   pool: {len(pool)}")

    candidates = sorted(pool.values(), key=lambda r: r["full_name"].lower())
    with open(os.path.join(args.out, "candidates.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(candidates)

    # Stratified sample: the same number of repositories from each band. A
    # band with fewer candidates than its share contributes all of them.
    rng = random.Random(args.seed)
    per_band = args.size // len(BANDS)
    sample = []
    for _, band in BANDS:
        members = [r for r in candidates if r["band"] == band]
        rng.shuffle(members)
        if len(members) < per_band:
            print(f"  band {band}: only {len(members)} candidates (wanted {per_band})")
        sample.extend(members[:per_band])
    with open(os.path.join(args.out, "sample.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sample)

    meta = {
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "topics": TOPICS, "bands": [b for _, b in BANDS],
        "pushed_since": args.pushed_since, "max_size_mb": args.max_size_mb,
        "pages_per_query": args.pages, "seed": args.seed,
        "candidates": len(candidates), "sample": len(sample),
        "sample_per_band": {band: sum(1 for r in sample if r["band"] == band) for _, band in BANDS},
    }
    with open(os.path.join(args.out, "selection.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"\n{len(candidates)} candidates, {len(sample)} selected -> {args.out}/sample.csv")


if __name__ == "__main__":
    main()
