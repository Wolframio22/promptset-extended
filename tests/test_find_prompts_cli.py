"""Integration tests for the find_prompts command-line entry point.

The file collection logic lives in the module's __main__ block, so these
tests run the program as a subprocess over temporary directories, exactly as
a user would. Several of them are regression tests for defects fixed during
the project.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# High run identifiers so the tests never overwrite the user's own results.
_RUN_ID_BASE = 900


def run_find_prompts(repo_dir, run_id, threads=2, extra=()):
    """Run the engine and return (completed process, parsed output or None)."""
    output = ROOT / "data" / f"repo_data_export_{run_id:03d}.json"
    output.unlink(missing_ok=True)
    completed = subprocess.run(
        [sys.executable, "-m", "gen_prompts.find_prompts",
         "--run_id", str(run_id), "--repo_dir", str(repo_dir),
         "--threads", str(threads), *extra],
        cwd=ROOT, capture_output=True, text=True, timeout=900,
    )
    data = json.loads(output.read_text()) if output.exists() else None
    output.unlink(missing_ok=True)
    return completed, data


def analysed_files(data, repo_dir):
    """Paths of the analysed files, relative to the repository."""
    return {str(Path(p).relative_to(repo_dir)) for p in data}


def write(path: Path, content="x = 1\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content)


def test_only_python_files_are_analysed(tmp_path):
    write(tmp_path / "main.py")
    write(tmp_path / "notes.txt", "plain text")
    write(tmp_path / "config.yaml", "key: value")
    write(tmp_path / "logo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF")

    completed, data = run_find_prompts(tmp_path, _RUN_ID_BASE + 1)

    assert completed.returncode == 0, completed.stderr
    assert analysed_files(data, tmp_path) == {"main.py"}


def test_dependency_and_external_directories_are_skipped(tmp_path):
    write(tmp_path / "src" / "app.py")
    for excluded in ("venv", "node_modules", "__pycache__", ".git", "testbed"):
        write(tmp_path / excluded / "module.py")

    completed, data = run_find_prompts(tmp_path, _RUN_ID_BASE + 2)

    assert completed.returncode == 0, completed.stderr
    assert analysed_files(data, tmp_path) == {"src/app.py"}


def test_extra_exclusions_from_command_line(tmp_path):
    write(tmp_path / "src" / "app.py")
    write(tmp_path / "vendor" / "lib.py")

    completed, data = run_find_prompts(
        tmp_path, _RUN_ID_BASE + 3, extra=("--exclude-dirs", "vendor"))

    assert completed.returncode == 0, completed.stderr
    assert analysed_files(data, tmp_path) == {"src/app.py"}


def test_fewer_files_than_threads(tmp_path):
    # Regression: the batch size was len(paths) // threads, which is zero
    # here and made the run abort with "n must be at least one".
    write(tmp_path / "only.py")

    completed, data = run_find_prompts(tmp_path, _RUN_ID_BASE + 4, threads=4)

    assert completed.returncode == 0, completed.stderr
    assert analysed_files(data, tmp_path) == {"only.py"}


def test_repository_without_python_files(tmp_path):
    # Regression: CodeR keeps every prompt in YAML and has no Python at all.
    write(tmp_path / "config" / "roles.yml", "role: editor")

    completed, data = run_find_prompts(tmp_path, _RUN_ID_BASE + 5, threads=4)

    assert completed.returncode == 0, completed.stderr
    assert data == {}


def test_invalid_utf8_does_not_abort_the_batch(tmp_path):
    # A single unreadable file must not stop the rest of the analysis.
    write(tmp_path / "broken.py", b"x = '\xff\xfe\xfd invalid utf-8'\n")
    write(tmp_path / "good.py", 'SYS_PROMPT = """You are a helpful assistant."""\n')

    completed, data = run_find_prompts(tmp_path, _RUN_ID_BASE + 6)

    assert completed.returncode == 0, completed.stderr
    assert "good.py" in analysed_files(data, tmp_path)
    good = next(v for k, v in data.items() if k.endswith("good.py"))
    assert good["used_prompt_or_template_name"]


@pytest.mark.slow
def test_more_than_5000_files_with_one_thread(tmp_path):
    # Regression: with a single thread, paths[:5000] silently dropped every
    # file beyond the first 5000 while reporting a successful run.
    total = 5005
    for i in range(total):
        write(tmp_path / f"f{i}.py")

    completed, data = run_find_prompts(tmp_path, _RUN_ID_BASE + 7, threads=1)

    assert completed.returncode == 0, completed.stderr
    assert len(data) == total
