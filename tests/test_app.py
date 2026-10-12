"""Tests of the graphical interface: texts, a few helper functions and a full run.

The last tests drive app.py with Streamlit's AppTest, without a browser and
without network access: they analyse a small folder created on the fly.
"""

import json
import string
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import app
import app_text

APP = Path(__file__).resolve().parents[1] / "app.py"
SOURCE = '''import openai

SYSTEM_PROMPT = """You are a careful code reviewer.
Answer in JSON with the fields "verdict" and "reason"."""

def review(code):
    client = openai.OpenAI()
    return client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": code}],
    )
'''


# ---------------------------------------------------------------------------
# Texts
# ---------------------------------------------------------------------------

def test_every_text_exists_in_every_language():
    for clave, entrada in app_text.TEXTOS.items():
        assert set(entrada) == set(app_text.IDIOMAS), clave
        assert all(valor.strip() for valor in entrada.values()), clave
        # The same placeholders in every language, or format() would fail.
        campos = {frozenset(c for _, c, _, _ in string.Formatter().parse(v) if c)
                  for v in entrada.values()}
        assert len(campos) == 1, clave


def test_every_heuristic_has_a_readable_name():
    for idioma in app_text.IDIOMAS:
        nombres = [app_text.nombre_heuristica(h, idioma) for h in app_text.HEURISTICAS]
        assert len(set(nombres)) == len(nombres) == 7


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def test_repository_addresses():
    assert app.normalizar_url("TheR1D/shell_gpt") == "https://github.com/TheR1D/shell_gpt"
    assert app.nombre_repositorio("https://github.com/TheR1D/shell_gpt") == "TheR1D/shell_gpt"
    assert app.nombre_repositorio("git@github.com:a/b.git") == "a/b"


def test_localizar_linea_finds_each_repeated_capture(tmp_path):
    fuente = tmp_path / "m.py"
    fuente.write_text("a = 1\nmsg = SystemMessage(content=x)\n\nmsg = SystemMessage(content=x)\n")
    assert app.localizar_linea(fuente, "SystemMessage(content=x)") == 2
    assert app.localizar_linea(fuente, "SystemMessage(content=x)", 2) == 4
    assert app.localizar_linea(fuente, "missing") is None


def test_reviews_are_saved_and_loaded(tmp_path):
    ruta = tmp_path / "rev.json"
    assert app.cargar_revisiones(ruta) == {}
    app.guardar_revisiones(ruta, {"k": {"es_prompt": "si"}})
    assert app.cargar_revisiones(ruta) == {"k": {"es_prompt": "si"}}


def test_export_includes_the_review():
    df = pd.DataFrame([{"repositorio": "r", "commit": "c", "archivo": "a.py", "linea": 3,
                        "heuristica": "used_in_openai_call", "prompt": "p", "_clave": "k1"}])
    salida = app.tabla_exportable(df, {"k1": {"es_prompt": "si", "valoracion": 4,
                                              "comentario": "ok"}}, "en")
    assert salida.loc[0, "tipo_deteccion"] == "OpenAI API call"
    assert salida.loc[0, "es_prompt"] == "si" and salida.loc[0, "valoracion"] == 4


# ---------------------------------------------------------------------------
# The whole interface, driven by AppTest
# ---------------------------------------------------------------------------

@pytest.fixture
def interfaz(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTSET_REVISIONES", str(tmp_path / "revisiones.json"))
    return AppTest.from_file(str(APP), default_timeout=120)


@pytest.mark.parametrize("idioma, titulo", [
    ("es", "Extractor de prompts"),
    ("en", "Prompt extractor"),
    ("ca", "Extractor de prompts"),
])
def test_interface_starts_in_every_language(interfaz, idioma, titulo):
    interfaz.run()
    interfaz.sidebar.selectbox[0].set_value(idioma).run()
    assert not interfaz.exception
    assert interfaz.title[0].value == titulo


def test_analyse_a_local_folder_then_review(interfaz, tmp_path):
    proyecto = tmp_path / "demo"
    proyecto.mkdir()
    (proyecto / "agent.py").write_text(SOURCE)

    # Analyse the folder: the results open by themselves.
    interfaz.run()
    interfaz.radio(key="origen").set_value("local").run()
    interfaz.text_input(key="ruta_local").set_value(str(proyecto)).run()
    next(b for b in interfaz.button if b.label == "Analizar").click().run()
    assert not interfaz.exception
    assert interfaz.session_state["vista"] == "resultados"
    resultados = interfaz.session_state["resultados"]
    assert {"used_prompt_or_template_name", "used_in_openai_call"} <= set(resultados["heuristica"])

    # Keep only the system prompt and mark it as a prompt in the review.
    interfaz.text_input(key="filtro_buscar").set_value("You are").run()
    assert len(interfaz.session_state["claves_filtradas"]) == 1
    interfaz.session_state["_ir_a"] = "revision"
    interfaz.run()
    next(r for r in interfaz.radio if r.label == "¿Es un prompt?").set_value("si").run()
    assert not interfaz.exception
    guardadas = json.loads((tmp_path / "revisiones.json").read_text())
    assert [v["es_prompt"] for v in guardadas.values()] == ["si"]

    # The review survives a change of language (this used to stop the app).
    interfaz.sidebar.selectbox[0].set_value("en").run()
    interfaz.session_state["_ir_a"] = "resultados"
    interfaz.run()
    assert not interfaz.exception
    assert {m.label: m.value for m in interfaz.metric}["Reviewed"] == f"1 / {len(resultados)}"


def test_local_folders_can_be_hidden_when_sharing_the_interface(interfaz, monkeypatch):
    monkeypatch.setenv("PROMPTSET_SOLO_GITHUB", "1")
    interfaz.run()
    assert interfaz.radio(key="origen").options == ["GitHub"]
