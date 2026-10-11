"""Aggregate the RQ3 results: tables, figures and a sample for manual checking.

Reads the folders written by run_study.py and writes, in --out:
  repos.csv              one row per repository: inventory, detections, type
  detections.csv         one row per detection of the final engine (tests excluded)
  heuristics.csv         detections per heuristic: original, final, kept, removed, added
  summary.json           every number quoted in the thesis
  tables.tex             the main numbers as LaTeX tables, ready to paste
  validation_sample.csv  random detections to label by hand (column es_prompt)
  figures/               PDF (for LaTeX) and PNG versions of each figure

Detections in test files are left out everywhere, with the same rule as in
the validation against the oracle: a folder called test, tests or testing,
or a file named test_*.py or *_test.py.

After labelling the sample (es_prompt = si / no / dudoso), run it again with
--labels to add the precision estimates:

    python study/rq3/analyze_study.py --labels study/rq3/analysis/validation_sample.csv
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

# The shared figure style lives one folder up (study/plotstyle.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ps = importlib.import_module("plotstyle")

# Internal heuristic names and the names used in the thesis and the interface.
HEURISTICS = {
    "used_prompt_or_template_name": "Variable con nombre de prompt",
    "used_in_openai_call": "Llamada a la API de OpenAI",
    "used_in_langchain_llm_call": "Plantilla o mensaje de LangChain",
    "used_chat_function": "Llamada a chat() o summarize()",
    "used_langchain_tool": "Herramienta declarada con @tool",
    "used_langchain_tool_class": "Herramienta declarada como clase",
    "find_from_file": "Plantilla cargada desde archivo",
}
BANDS = ["20-99", "100-499", "500-1999", "2000+"]
BAND_LABELS = {"20-99": "20–99", "100-499": "100–499", "500-1999": "500–1.999",
               "2000+": "2.000 o más"}
TEST_DIRS = {"test", "tests", "testing"}
BINS = [(0, 0, "0"), (1, 5, "1–5"), (6, 10, "6–10"), (11, 25, "11–25"), (26, 50, "26–50"),
        (51, 100, "51–100"), (101, 250, "101–250"), (251, None, "> 250")]

# Project type, from the GitHub topics and description plus a few library
# signals. A repository can have several types. It is an approximation and is
# reported as such.
TYPE_RULES = [
    ("Agente", r"\bagents?\b|agentic|multi-agent|autonomous|autogpt|\bcrew",
     {"AutoGen", "CrewAI", "LangGraph", "smolagents", "PydanticAI"}),
    ("RAG o consulta de documentos",
     (r"\brag\b|retrieval|vector|embedding|knowledge[- ]base|question[- ]answering|"
      r"chat[- ]with[- ]|\bdocuments?\b|\bpdfs?\b"), {"LlamaIndex", "Haystack"}),
    ("Chatbot o asistente", r"chat-?bot|assistant|telegram|discord|wechat|slack|\bbot\b", set()),
    ("Herramienta para programadores",
     (r"code[- ]?gen|coding|code[- ]review|developer|devtools?|copilot|programming|"
      r"software[- ]engineering|\bcli\b|terminal|command[- ]line|\bcommits?\b|\bide\b|vscode"),
     set()),
    ("Framework o biblioteca", r"framework|\bsdk\b|\blibrary\b|toolkit", set()),
    ("Investigación o evaluación",
     r"benchmark|evaluation|\bpaper\b|official (code|implementation)|reproduc|\bdatasets?\b",
     set()),
]

# Features of the prompt text, measured on detections that contain the text
# itself (not only a reference to a variable).
STRING_RE = re.compile(r'(?<![A-Za-z0-9_])([rRbBuUfF]{0,2})("""|\'\'\'|"|\')(.*?)(?<!\\)\2', re.DOTALL)
WORD_RE = re.compile(r"[A-Za-zÀ-ɏ]{2,}|[一-鿿]")
FEATURES = {
    "template": "Plantilla con variables",
    "multiline": "Texto de varias líneas",
    "markdown": "Estructura Markdown (títulos o listas)",
    "role": "Define un rol («You are…»)",
    "json": "Pide o menciona JSON",
    "examples": "Incluye ejemplos",
    "xml": "Usa etiquetas XML",
    "step": "Pide razonar paso a paso",
    "cjk": "Escrito en chino, japonés o coreano",
}
PLACEHOLDER_RES = [
    re.compile(r"\{[A-Za-z_]\w*(\.\w+)*(\[[^\]]*\])?(![rsa])?(:[^{}]*)?\}"),   # str.format
    re.compile(r"\{\{\s*[A-Za-z_][\w.]*\s*\}\}|\{%"),                             # Jinja
    re.compile(r"\$\{?[A-Za-z_]\w*"),                                              # string.Template
    re.compile(r"%\([A-Za-z_]\w*\)[sd]|%s"),                                       # printf style
]
FSTRING_FIELD = re.compile(r"(?<!\{)\{(?!\{)[^{}]+\}")
ROLE_RE = re.compile(r"(?im)^\W{0,5}(you are|you're|you will act|act as|your role is|"
                     r"eres un|eres una|你是)")
EXAMPLES_RE = re.compile(r"(?im)^\W{0,5}(examples?|ejemplos?)\b\s*\d*\s*[:#\-]|<examples?>")
STEP_RE = re.compile(r"step[- ]by[- ]step|let'?s think|think (carefully|step)|"
                     r"chain[- ]of[- ]thought|paso a paso", re.IGNORECASE)
XML_RE = re.compile(r"<([A-Za-z_][\w-]{1,30})>[\s\S]*?</\1>")
CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def is_test_file(rel: str) -> bool:
    parts = rel.lower().split("/")
    name = parts[-1]
    return (any(p in TEST_DIRS for p in parts[:-1]) or name.startswith("test_")
            or name.endswith("_test.py"))


def median(values):
    return statistics.median(values) if values else 0


def quartiles(values):
    if len(values) < 2:
        return (values[0], values[0]) if values else (0, 0)
    q = statistics.quantiles(values, n=4, method="inclusive")
    return q[0], q[2]


def share(part, whole):
    return 100 * part / whole if whole else 0.0


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return result


def spearman(x, y):
    """Spearman rank correlation (Pearson correlation of the ranks)."""
    if len(x) < 3:
        return float("nan")
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (sx * sy) if sx and sy else float("nan")


def wilson(k, n, z=1.96):
    """95 % Wilson interval for a proportion."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d, (c + r) / d


def normalise(text: str) -> str:
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Prompt text features
# --------------------------------------------------------------------------

def literal_parts(code: str):
    """String literals of a captured fragment that contain natural language."""
    parts = []
    for prefix, _quote, body in STRING_RE.findall(code):
        if len(WORD_RE.findall(body)) >= 3:
            parts.append(("f" in prefix.lower(), body))
    return parts


def has_placeholder(is_f: bool, body: str) -> bool:
    if is_f and FSTRING_FIELD.search(body):
        return True
    return any(regex.search(body) for regex in PLACEHOLDER_RES)


def prompt_features(code: str) -> dict:
    parts = literal_parts(code)
    if not parts:
        return {"kind": "referencia", "chars": 0, "words": 0, **{f: 0 for f in FEATURES}}
    text = "\n".join(body for _, body in parts)
    lists = len(re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+\S", text))
    return {
        "kind": "literal",
        "chars": len(text),
        "words": len(WORD_RE.findall(text)),
        "template": int(any(has_placeholder(f, b) for f, b in parts)),
        "multiline": int(any("\n" in b or "\\n" in b for _, b in parts)),
        "markdown": int(bool(re.search(r"(?m)^\s*#{1,4}\s+\S", text)) or lists >= 2),
        "role": int(bool(ROLE_RE.search(text))),
        "json": int(bool(re.search(r"\bjson\b", text, re.IGNORECASE))),
        "examples": int(bool(EXAMPLES_RE.search(text))),
        "xml": int(bool(XML_RE.search(text))),
        "step": int(bool(STEP_RE.search(text))),
        "cjk": int(bool(CJK_RE.search(text))),
    }


def project_types(meta: dict) -> list:
    text = (meta.get("topics", "").replace(";", " ") + " " + meta.get("description", "")).lower()
    libraries = set(meta.get("libraries", []))
    found = []
    for label, pattern, libs in TYPE_RULES:
        signal = bool(re.search(pattern, text)) or bool(libraries & libs)
        if label.startswith("RAG") and meta.get("vector_stores"):
            signal = True
        if signal:
            found.append(label)
    return found or ["Otros"]


# --------------------------------------------------------------------------
# Loading and per-repository aggregation
# --------------------------------------------------------------------------

def load(results: Path):
    repos = []
    for folder in sorted(p for p in results.iterdir() if p.is_dir()):
        if not (folder / "done").exists() or not (folder / "meta.json").exists():
            continue
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        records = {}
        for engine in ("final", "original"):
            path = folder / f"{engine}.json"
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if isinstance(data, dict):           # older format: {file: {heuristic: [text]}}
                data = [{"file": f, "line": None, "heuristic": h, "text": t}
                        for f, hs in data.items() for h, ts in hs.items() for t in ts]
            records[engine] = data
        repos.append((meta, records))
    return repos


def failure(meta: dict) -> str:
    error = meta.get("error", "")
    if "clone" in error:
        return "No se pudo clonar"
    if "final:" in error:
        return "Error del motor final"
    if "original:" in error:
        return "Error del motor original"
    return ""


def compare(final, original):
    """Mark each detection as kept, added (final only) or removed (original only)."""
    def key(r):
        return r["file"], r["heuristic"], normalise(r["text"])

    count_final, count_original = Counter(map(key, final)), Counter(map(key, original))
    kept_budget = {k: min(count_final[k], count_original.get(k, 0)) for k in count_final}
    used = Counter()
    for r in final:
        k = key(r)
        r["status"] = "conservada" if used[k] < kept_budget.get(k, 0) else "nueva"
        used[k] += 1
    used = Counter()
    for r in original:
        k = key(r)
        r["status"] = "conservada" if used[k] < kept_budget.get(k, 0) else "eliminada"
        used[k] += 1


def build(repos):
    rows, detections, removed = [], [], []
    for meta, records in repos:
        fail = failure(meta)
        final = [r for r in records["final"] if not is_test_file(r["file"])]
        original = [r for r in records["original"] if not is_test_file(r["file"])]
        tests_final = len(records["final"]) - len(final)
        compare(final, original)
        name, commit = meta["full_name"], meta.get("commit", "")
        types = project_types(meta)
        kloc = meta.get("py_loc", 0) / 1000
        in_prompt_files = sum(1 for r in final if "prompt" in r["file"].lower())
        row = {
            "full_name": name, "band": meta.get("band", ""), "stars": int(meta.get("stars") or 0),
            "created_year": (meta.get("created_at") or "")[:4], "license": meta.get("license", ""),
            "topics": meta.get("topics", ""), "description": meta.get("description", ""),
            "status": fail or "Analizado", "commit": commit,
            "py_files": meta.get("py_files", 0), "py_loc": meta.get("py_loc", 0),
            "notebooks": meta.get("notebooks", 0),
            "libraries": ";".join(meta.get("libraries", [])),
            "n_libraries": len(meta.get("libraries", [])),
            "vector_stores": ";".join(meta.get("vector_stores", [])),
            "http_model_calls": int(bool(meta.get("http_model_calls"))),
            "prompt_files_outside_py": meta.get("prompt_files_outside_py", 0),
            "types": ";".join(types),
            "detections_final": len(final), "files_final": len({r["file"] for r in final}),
            "detections_original": len(original),
            "files_original": len({r["file"] for r in original}),
            "kept": sum(r["status"] == "conservada" for r in final),
            "added": sum(r["status"] == "nueva" for r in final),
            "removed": sum(r["status"] == "eliminada" for r in original),
            "test_detections_final": tests_final,
            "detections_per_kloc": round(len(final) / kloc, 3) if kloc else 0,
            "share_in_prompt_files": round(share(in_prompt_files, len(final)), 1) if final else 0,
            "heuristics_final": ";".join(sorted({r["heuristic"] for r in final})),
            "final_seconds": meta.get("final_seconds", 0),
            "original_seconds": meta.get("original_seconds", 0),
            "error": meta.get("error", "").strip()[:300],
        }
        rows.append(row)
        if fail:
            continue
        for r in final:
            feats = prompt_features(r["text"])
            line = r.get("line") or ""
            detections.append({
                "repository": name, "band": row["band"], "file": r["file"], "line": line,
                "heuristic": r["heuristic"], "heuristic_name": HEURISTICS.get(r["heuristic"], r["heuristic"]),
                "status": r["status"],
                "url": f"https://github.com/{name}/blob/{commit}/{r['file']}" + (f"#L{line}" if line else ""),
                "in_prompt_file": int("prompt" in r["file"].lower()),
                **feats, "text": r["text"][:3000],
            })
        for r in original:
            if r["status"] == "eliminada":
                line = r.get("line") or ""
                removed.append({
                    "repository": name, "file": r["file"], "line": line, "heuristic": r["heuristic"],
                    "url": f"https://github.com/{name}/blob/{commit}/{r['file']}" + (f"#L{line}" if line else ""),
                    "text": r["text"][:3000],
                })
    return rows, detections, removed


# --------------------------------------------------------------------------
# Summary numbers
# --------------------------------------------------------------------------

def summarise(rows, detections, removed):
    analysed = [r for r in rows if r["status"] == "Analizado"]
    with_py = [r for r in analysed if r["py_files"] > 0]
    population = [r for r in with_py if r["detections_final"] > 0]   # repositories with prompts
    n_pop = len(population)
    det = [r["detections_final"] for r in population]
    files = [r["files_final"] for r in population]
    density = [r["detections_per_kloc"] for r in population]
    q1, q3 = quartiles(det)

    libraries = Counter(lib for r in population for lib in r["libraries"].split(";") if lib)
    libraries_all = Counter(lib for r in with_py for lib in r["libraries"].split(";") if lib)
    pairs = Counter()
    for r in population:
        libs = sorted(lib for lib in r["libraries"].split(";") if lib)
        pairs.update(f"{a} + {b}" for i, a in enumerate(libs) for b in libs[i + 1:])
    types = Counter(t for r in population for t in r["types"].split(";"))

    literal = [d for d in detections if d["kind"] == "literal"]
    heur_final = Counter(d["heuristic"] for d in detections)
    heur_repos = Counter(h for r in population for h in r["heuristics_final"].split(";") if h)

    by_band = {}
    for band in BANDS:
        members = [r for r in with_py if r["band"] == band]
        with_prompts = [r for r in members if r["detections_final"] > 0]
        by_band[band] = {
            "selected": sum(1 for r in rows if r["band"] == band),
            "analysed": sum(1 for r in analysed if r["band"] == band),
            "with_py": len(members),
            "with_llm_library": sum(1 for r in members if r["libraries"]),
            "with_prompts": len(with_prompts),
            "pct_with_prompts": round(share(len(with_prompts), len(members)), 1),
            "median_detections_with_prompts": median([r["detections_final"] for r in with_prompts]),
            "median_detections_all": median([r["detections_final"] for r in members]),
        }

    total_final = sum(r["detections_final"] for r in with_py)
    total_original = sum(r["detections_original"] for r in with_py)
    summary = {
        "sample": {
            "selected": len(rows),
            "analysed": len(analysed),
            "failures": dict(Counter(r["status"] for r in rows if r["status"] != "Analizado")),
            "with_python": len(with_py),
            "with_llm_library": sum(1 for r in with_py if r["libraries"]),
            "with_http_model_calls": sum(1 for r in with_py if r["http_model_calls"]),
            "with_llm_library_or_http": sum(1 for r in with_py if r["libraries"] or r["http_model_calls"]),
            "with_prompts_final": n_pop,
            "pct_with_prompts_final": round(share(n_pop, len(with_py)), 1),
            "with_prompts_original": sum(1 for r in with_py if r["detections_original"] > 0),
            "by_band": by_band,
        },
        "density": {
            "median_detections": median(det), "q1": q1, "q3": q3,
            "mean_detections": round(statistics.fmean(det), 1) if det else 0,
            "max_detections": max(det, default=0),
            "median_files": median(files),
            "median_detections_per_kloc": round(median(density), 2),
            "top_repositories": sorted(((r["detections_final"], r["full_name"]) for r in population),
                                       reverse=True)[:10],
            "spearman_stars_detections": round(spearman([r["stars"] for r in with_py],
                                                        [r["detections_final"] for r in with_py]), 3),
            "spearman_loc_detections": round(spearman([r["py_loc"] for r in with_py],
                                                      [r["detections_final"] for r in with_py]), 3),
            "repos_prompts_mostly_in_prompt_files": sum(1 for r in population
                                                        if r["share_in_prompt_files"] >= 50),
            "repos_with_any_prompt_file_detection": sum(1 for r in population
                                                        if r["share_in_prompt_files"] > 0),
        },
        "libraries": {
            "population": n_pop,
            "counts": dict(libraries.most_common()),
            "pct": {k: round(share(v, n_pop), 1) for k, v in libraries.most_common()},
            "pct_all_with_python": {k: round(share(v, len(with_py)), 1)
                                    for k, v in libraries_all.most_common()},
            "none_recognised": sum(1 for r in population if not r["libraries"]),
            "median_libraries": median([r["n_libraries"] for r in population]),
            "top_pairs": pairs.most_common(8),
            "with_vector_store": sum(1 for r in population if r["vector_stores"]),
            "with_http_model_calls": sum(1 for r in population if r["http_model_calls"]),
        },
        "types": {k: {"repos": v, "pct": round(share(v, n_pop), 1)} for k, v in types.most_common()},
        "where_prompts_live": {
            "repos_with_prompt_files_outside_py": sum(1 for r in population
                                                      if r["prompt_files_outside_py"] > 0),
            "pct_repos_with_prompt_files_outside_py": round(share(
                sum(1 for r in population if r["prompt_files_outside_py"] > 0), n_pop), 1),
            "repos_with_notebooks": sum(1 for r in population if r["notebooks"] > 0),
            "test_detections_excluded": sum(r["test_detections_final"] for r in with_py),
        },
        "heuristics_final": {
            HEURISTICS.get(h, h): {"detections": heur_final.get(h, 0),
                                   "pct_detections": round(share(heur_final.get(h, 0), len(detections)), 1),
                                   "repos": heur_repos.get(h, 0),
                                   "pct_repos": round(share(heur_repos.get(h, 0), n_pop), 1)}
            for h in HEURISTICS
        },
        "prompts": {
            "detections": len(detections),
            "literal": len(literal),
            "pct_literal": round(share(len(literal), len(detections)), 1),
            "median_chars_literal": median([d["chars"] for d in literal]),
            "median_words_literal": median([d["words"] for d in literal]),
            "features_pct_of_literal": {FEATURES[f]: round(share(sum(d[f] for d in literal), len(literal)), 1)
                                        for f in FEATURES},
        },
        "comparison": {
            "detections_original": total_original,
            "detections_final": total_final,
            "change_pct": round(share(total_final - total_original, total_original), 1),
            "kept": sum(r["kept"] for r in with_py),
            "removed": sum(r["removed"] for r in with_py),
            "added": sum(r["added"] for r in with_py),
            "files_original": sum(r["files_original"] for r in with_py),
            "files_final": sum(r["files_final"] for r in with_py),
            "repos_original": sum(1 for r in with_py if r["detections_original"] > 0),
            "repos_final": n_pop,
            "median_detections_original": median([r["detections_original"] for r in with_py
                                                  if r["detections_original"] > 0]),
            "median_detections_final": median(det),
            "seconds_original": round(sum(r["original_seconds"] for r in analysed), 1),
            "seconds_final": round(sum(r["final_seconds"] for r in analysed), 1),
            "median_seconds_original": median([r["original_seconds"] for r in analysed]),
            "median_seconds_final": median([r["final_seconds"] for r in analysed]),
        },
    }
    c = summary["comparison"]
    c["speedup"] = round(c["seconds_original"] / c["seconds_final"], 2) if c["seconds_final"] else None
    per_heuristic = []
    for h, name in HEURISTICS.items():
        per_heuristic.append({
            "heuristic": h, "name": name,
            "original": sum(1 for d in detections if d["heuristic"] == h and d["status"] == "conservada")
            + sum(1 for d in removed if d["heuristic"] == h),
            "final": heur_final.get(h, 0),
            "kept": sum(1 for d in detections if d["heuristic"] == h and d["status"] == "conservada"),
            "removed": sum(1 for d in removed if d["heuristic"] == h),
            "added": sum(1 for d in detections if d["heuristic"] == h and d["status"] == "nueva"),
        })
    return summary, per_heuristic


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def figures(rows, detections, summary, per_heuristic, out: Path):
    ps.setup()
    figdir = out / "figures"
    with_py = [r for r in rows if r["status"] == "Analizado" and r["py_files"] > 0]
    n_pop = summary["sample"]["with_prompts_final"]

    # 1. Libraries in repositories with prompts (top 12, the rest folded).
    lib = summary["libraries"]["counts"]
    items = sorted(lib.items(), key=lambda kv: -kv[1])
    head, tail = items[:12], items[12:]
    labels = [k for k, _ in head]
    values = [share(v, n_pop) for _, v in head]
    if tail:
        others = sum(1 for r in with_py if r["detections_final"] > 0 and
                     set(r["libraries"].split(";")) & {k for k, _ in tail})
        labels.append(f"Otras ({len(tail)} bibliotecas)")
        values.append(share(others, n_pop))
    if labels:
        ps.hbars(labels, values, figdir / "rq3_bibliotecas", value_text=ps.pct,
                 xmax=max(values) * 1.05,
                 note=f"Sobre {ps.num(n_pop)} repositorios con prompts. Un repositorio puede usar varias.")

    # 2. Detections per repository (all analysed repositories with Python code).
    counts = [r["detections_final"] for r in with_py]
    bins = []
    for low, high, label in BINS:
        bins.append(sum(1 for c in counts if c >= low and (high is None or c <= high)))
    ps.columns([b[2] for b in BINS], bins, figdir / "rq3_detecciones_por_repo",
               xlabel="Prompts detectados por repositorio")

    # 3. Detections per repository by star band.
    groups = [BAND_LABELS[b] for b in BANDS]
    series = [[r["detections_final"] for r in with_py if r["band"] == b] for b in BANDS]
    if any(series):
        ps.strip_by_group(groups, series, figdir / "rq3_por_popularidad",
                          ylabel="Prompts detectados (escala log.)",
                          xlabel="Estrellas en GitHub")

    # 4. Original vs final per heuristic.
    order = sorted(per_heuristic, key=lambda h: -max(h["final"], h["original"]))
    order = [h for h in order if h["final"] or h["original"]]
    if order:
        ps.dumbbell([h["name"] for h in order], [h["original"] for h in order],
                    [h["final"] for h in order], figdir / "rq3_heuristicas_original_final",
                    xlabel="Detecciones en la muestra (escala log.)")

    # 5. Original vs final per repository.
    x = [r["detections_original"] for r in with_py]
    y = [r["detections_final"] for r in with_py]
    if x:
        ps.scatter_compare(x, y, figdir / "rq3_repos_original_final",
                           xlabel="Detecciones de PromptSet original",
                           ylabel="Detecciones de promptset-extended",
                           note_below="Por debajo de la diagonal:\nmenos detecciones en la versión final")

    # 6. How prompts are written (detections that contain the text).
    feats = summary["prompts"]["features_pct_of_literal"]
    items = sorted(feats.items(), key=lambda kv: -kv[1])
    if summary["prompts"]["literal"]:
        ps.hbars([k for k, _ in items], [v for _, v in items], figdir / "rq3_rasgos_prompts",
                 value_text=ps.pct, xmax=max(v for _, v in items) * 1.05 or 1,
                 note=f"Sobre {ps.num(summary['prompts']['literal'])} detecciones que contienen el texto del prompt.")

    # 7. Project types.
    types = summary["types"]
    items = sorted(types.items(), key=lambda kv: (kv[0] == "Otros", -kv[1]["repos"]))
    if items:
        ps.hbars([k for k, _ in items], [v["pct"] for _, v in items], figdir / "rq3_tipos_proyecto",
                 value_text=ps.pct, xmax=max(v["pct"] for _, v in items) * 1.05,
                 note=f"Sobre {ps.num(n_pop)} repositorios con prompts. Un repositorio puede tener varios tipos.")


# --------------------------------------------------------------------------
# Manual validation sample and its results
# --------------------------------------------------------------------------

def validation_sample(detections, removed, out: Path, sizes, seed=42):
    path = out / "validation_sample.csv"
    if path.exists():
        with open(path, newline="", encoding="utf-8-sig") as f:
            if any((row.get("es_prompt") or "").strip() for row in csv.DictReader(f)):
                print(f"[keep] {path} already has labels; it is not overwritten.")
                return
    rng = random.Random(seed)
    def sort_key(d):
        return d["repository"], d["file"], str(d["line"]), d["heuristic"], d["text"]

    pools = {
        "conservada": sorted((d for d in detections if d["status"] == "conservada"), key=sort_key),
        "nueva": sorted((d for d in detections if d["status"] == "nueva"), key=sort_key),
        "eliminada": sorted(removed, key=sort_key),
    }
    rows = []
    for group, size in sizes.items():
        pool = pools[group]
        for d in rng.sample(pool, min(size, len(pool))):
            text = d["text"] if len(d["text"]) <= 1500 else d["text"][:1500] + " […]"
            rows.append({"id": len(rows) + 1, "grupo": group, "repositorio": d["repository"],
                         "archivo": d["file"], "linea": d["line"],
                         "heuristica": HEURISTICS.get(d["heuristic"], d["heuristic"]),
                         "enlace": d["url"], "texto": text, "es_prompt": "", "comentario": ""})
    rng.shuffle(rows)             # mixed order, so the group does not bias the labelling
    for i, row in enumerate(rows, 1):
        row["orden"] = i
    fields = ["orden", "id", "grupo", "repositorio", "archivo", "linea", "heuristica", "enlace",
              "texto", "es_prompt", "comentario"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[sample] {len(rows)} detections to label -> {path}")


def read_labels(path: Path):
    yes, no, doubt = {"si", "sí", "s", "yes", "y", "1"}, {"no", "n", "0"}, {"dudoso", "d", "?"}
    groups = defaultdict(Counter)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            value = (row.get("es_prompt") or "").strip().lower()
            label = "si" if value in yes else "no" if value in no else "dudoso" if value in doubt else ""
            groups[row["grupo"]][label or "sin_etiqueta"] += 1
    return groups


def estimate(groups, summary, draws=20000, seed=42):
    """Share of real prompts per group and, combining groups, per engine."""
    comp = summary["comparison"]
    sizes = {"conservada": comp["kept"], "nueva": comp["added"], "eliminada": comp["removed"]}
    result = {"groups": {}}
    for g, c in groups.items():
        k, n = c["si"], c["si"] + c["no"]
        lo, hi = wilson(k, n)
        result["groups"][g] = {"si": c["si"], "no": c["no"], "dudoso": c["dudoso"],
                               "sin_etiqueta": c["sin_etiqueta"],
                               "pct_prompt": round(share(k, n), 1),
                               "ci95": [round(100 * lo, 1), round(100 * hi, 1)],
                               "pct_prompt_doubtful_as_no": round(share(k, n + c["dudoso"]), 1)}
    rng = random.Random(seed)

    def draw(g):
        c = groups.get(g, Counter())
        return rng.betavariate(c["si"] + 1, c["no"] + 1)

    finals, originals = [], []
    for _ in range(draws):
        pk, pa, pr = draw("conservada"), draw("nueva"), draw("eliminada")
        nk, na, nr = sizes["conservada"], sizes["nueva"], sizes["eliminada"]
        if nk + na:
            finals.append((pk * nk + pa * na) / (nk + na))
        if nk + nr:
            originals.append((pk * nk + pr * nr) / (nk + nr))

    def interval(values):
        values = sorted(values)
        if not values:
            return None
        return [round(100 * values[int(0.025 * len(values))], 1), round(100 * statistics.median(values), 1),
                round(100 * values[int(0.975 * len(values)) - 1], 1)]

    result["precision_final"] = interval(finals)        # [low, median, high] in %
    result["precision_original"] = interval(originals)
    pr = result["groups"].get("eliminada", {}).get("pct_prompt", 0)
    pa = result["groups"].get("nueva", {}).get("pct_prompt", 0)
    result["estimated_real_prompts_removed"] = round(sizes["eliminada"] * pr / 100)
    result["estimated_real_prompts_added"] = round(sizes["nueva"] * pa / 100)
    return result


# --------------------------------------------------------------------------
# LaTeX tables
# --------------------------------------------------------------------------

def tex_pct(v, decimals=1):
    return ps.num(v, decimals) + "\\,\\%"


def tex_table(caption, label, columns, header, rows, total=None):
    """A booktabs table as a list of LaTeX lines (one row per list of cells)."""
    def line(cells):
        return "    " + " & ".join(str(c) for c in cells) + r" \\"

    def head(text):
        # A header may span two lines ("Con\nPython"): a nested tabular keeps
        # them centred without extra packages.
        if not text:
            return ""
        if "\n" not in text:
            return f"\\textbf{{{text}}}"
        rows = r" \\ ".join(f"\\textbf{{{t}}}" for t in text.split("\n"))
        return f"\\begin{{tabular}}[b]{{@{{}}c@{{}}}}{rows}\\end{{tabular}}"

    out = [r"\begin{table}[H]", r"  \centering", r"  \small", f"  \\caption{{{caption}}}",
           f"  \\label{{{label}}}", f"  \\begin{{tabular}}{{{columns}}}", r"    \toprule",
           line(head(h) for h in header), r"    \midrule"]
    out += [line(r) for r in rows]
    if total:
        out += [r"    \midrule", line(total)]
    out += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""]
    return out


def signed(a, b):
    """Difference b - a as '+12 (+3,4 %)', with a proper minus sign in LaTeX."""
    if not a:
        return "--"
    sign = "+" if b >= a else "$-$"
    return f"{sign}{ps.num(abs(b - a))} ({sign}{tex_pct(abs(share(b - a, a)))})"


def tables(summary, per_heuristic, out: Path):
    s, c = summary["sample"], summary["comparison"]
    lines = ["% Tables generated by study/rq3/analyze_study.py. Do not edit the numbers by hand:",
             "% run the script again instead.", ""]

    keys = ("selected", "analysed", "with_py", "with_llm_library", "with_prompts")
    rows, total = [], Counter()
    for band in BANDS:
        b = s["by_band"][band]
        rows.append([BAND_LABELS[band], *(b[k] for k in keys[:-1]),
                     f"{b['with_prompts']} ({tex_pct(b['pct_with_prompts'])})"])
        total.update({k: b[k] for k in keys})
    lines += tex_table(
        "Composición de la muestra por popularidad (estrellas en GitHub).", "tab:rq3-muestra",
        "lrrrrr",
        ["Estrellas", "Seleccio-\nnados", "Analizados", "Con\nPython", "Con biblioteca\nde LLM",
         "Con\nprompts"],
        rows,
        [r"\textbf{Total}", *(total[k] for k in keys[:-1]),
         f"{total['with_prompts']} ({tex_pct(share(total['with_prompts'], total['with_py']))})"])

    lines += tex_table(
        "PromptSet original frente a promptset-extended sobre la misma muestra.",
        "tab:rq3-original-final", "lrrr",
        ["", "PromptSet\noriginal", "promptset-\nextended", "Diferencia"],
        [["Repositorios con detecciones", ps.num(c["repos_original"]), ps.num(c["repos_final"]),
          signed(c["repos_original"], c["repos_final"])],
         ["Archivos con detecciones", ps.num(c["files_original"]), ps.num(c["files_final"]),
          signed(c["files_original"], c["files_final"])],
         ["Detecciones", ps.num(c["detections_original"]), ps.num(c["detections_final"]),
          signed(c["detections_original"], c["detections_final"])],
         ["Mediana por repositorio", ps.num(c["median_detections_original"], 1),
          ps.num(c["median_detections_final"], 1), ""],
         ["Tiempo total de análisis", f"{ps.num(c['seconds_original'] / 60, 1)} min",
          f"{ps.num(c['seconds_final'] / 60, 1)} min", ""],
         ["Tiempo mediano por repositorio", f"{ps.num(c['median_seconds_original'], 2)} s",
          f"{ps.num(c['median_seconds_final'], 2)} s", ""]])

    fields = ("original", "final", "kept", "removed", "added")
    rows = [[h["name"].replace("@", r"\texttt{@}"), *(ps.num(h[f]) for f in fields)]
            for h in sorted(per_heuristic, key=lambda h: -h["original"])]
    lines += tex_table(
        "Detecciones por heurística: conservadas, eliminadas y nuevas en la versión final.",
        "tab:rq3-heuristicas", "lrrrrr",
        ["Heurística", "Original", "Final", "Conser-\nvadas", "Elimi-\nnadas", "Nuevas"], rows,
        [r"\textbf{Total}", *(ps.num(sum(h[f] for h in per_heuristic)) for f in fields)])

    v = summary.get("validation")
    if v:
        names = {"conservada": "Conservadas", "eliminada": "Eliminadas", "nueva": "Nuevas"}
        rows = []
        for g in ("conservada", "eliminada", "nueva"):
            if g in v["groups"]:
                x = v["groups"][g]
                interval = f"{ps.num(x['ci95'][0], 1)}--{tex_pct(x['ci95'][1])}"
                rows.append([names[g], x["si"] + x["no"] + x["dudoso"], x["si"], x["no"],
                             x["dudoso"], f"{tex_pct(x['pct_prompt'])} ({interval})"])
        lines += tex_table(
            ("Revisión manual de una muestra aleatoria de detecciones. Conservadas: las detectan "
             "ambas versiones; eliminadas: solo la original; nuevas: solo la final."),
            "tab:rq3-validacion",
            "lrrrrc", ["Grupo", "Revi-\nsadas", "Prompt", "No\nprompt", "Dudoso",
                              "\\% de prompts\n(IC 95\\,\\%)"], rows)
        rows = []
        for name, key, n in (("PromptSet original", "precision_original", c["detections_original"]),
                             ("promptset-extended", "precision_final", c["detections_final"])):
            if v.get(key):
                low, mid, high = v[key]
                rows.append([name, ps.num(n), tex_pct(mid), f"{ps.num(low, 1)}--{tex_pct(high)}",
                             ps.num(round(n * mid / 100))])
        if rows:
            lines += tex_table(
                "Precisión estimada de cada versión sobre la muestra completa.", "tab:rq3-precision",
                "lrrcr", ["Versión", "Detec-\nciones", "Precisión", "Intervalo\n95\\,\\%",
                          "Prompts reales\nestimados"], rows)
    (out / "tables.tex").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def write_csv(path: Path, rows, fields=None):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", default="study/rq3/results")
    parser.add_argument("--out", default="study/rq3/analysis")
    parser.add_argument("--labels", help="validation_sample.csv with the column es_prompt filled in")
    parser.add_argument("--sample-kept", type=int, default=100)
    parser.add_argument("--sample-removed", type=int, default=50)
    parser.add_argument("--sample-added", type=int, default=30)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    repos = load(Path(args.results))
    if not repos:
        sys.exit(f"No finished repositories in {args.results}.")
    rows, detections, removed = build(repos)
    summary, per_heuristic = summarise(rows, detections, removed)
    if args.labels:
        summary["validation"] = estimate(read_labels(Path(args.labels)), summary)

    write_csv(out / "repos.csv", rows)
    write_csv(out / "detections.csv", detections)
    write_csv(out / "heuristics.csv", per_heuristic)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    tables(summary, per_heuristic, out)
    validation_sample(detections, removed, out, {"conservada": args.sample_kept,
                                                 "eliminada": args.sample_removed,
                                                 "nueva": args.sample_added})
    if not args.no_figures:
        figures(rows, detections, summary, per_heuristic, out)

    s, c = summary["sample"], summary["comparison"]
    print(f"{s['analysed']} of {s['selected']} repositories analysed; "
          f"{s['with_prompts_final']} with prompts ({s['pct_with_prompts_final']} % of those with Python).")
    print(f"Detections: original {c['detections_original']}, final {c['detections_final']} "
          f"({c['change_pct']} %); kept {c['kept']}, removed {c['removed']}, added {c['added']}.")
    print(f"Outputs in {out}/")


if __name__ == "__main__":
    main()
