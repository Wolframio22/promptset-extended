"""
Graphical interface for promptset-extended.

Place this file at the repository root (next to the gen_prompts/ package)
and run:

    streamlit run app.py

Two views:
  1. Analysis -> pick repositories (local folder or URLs) and run the engine
  2. Results  -> browse the detected prompts and jump to the source code
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent          # engine root (gen_prompts/)
DIR_CLONES = RAIZ / "workspace"                 # cloned repositories land here
DIR_DATOS = RAIZ / "data"                       # engine output directory

st.set_page_config(page_title="promptset-extended", layout="wide")

# The engine runs as a subprocess with this same interpreter, so the virtual
# environment must be active before launching Streamlit.
try:
    import tree_sitter  # noqa: F401
except ImportError:
    st.error("No se encuentra tree-sitter. Activa el entorno virtual antes "
             "de lanzar la interfaz:\n\n"
             "    source venv/bin/activate\n"
             "    streamlit run app.py")
    st.stop()


# ---------------------------------------------------------------------------
# Core logic, kept free of Streamlit so it can be tested on its own
# ---------------------------------------------------------------------------

def contar_py(carpeta: Path) -> int:
    """Count .py files, skipping dependency directories."""
    excluidos = {".git", ".venv", "venv", "env", "node_modules",
                 "__pycache__", "testbed"}
    total = 0
    for ruta in carpeta.rglob("*.py"):
        if any(p in excluidos for p in ruta.parts):
            continue
        total += 1
    return total


def es_repositorio(carpeta: Path) -> bool:
    """Tell whether a directory is a repository of its own.

    Counting .py files is not enough: a single repository usually has source
    subdirectories that would be mistaken for separate repositories. The
    presence of a .git directory is the reliable signal.
    """
    return (carpeta / ".git").exists()


def clonar(url: str) -> Path:
    """Clone a repository into the workspace and return its path.

    Two repositories can share the same final name (for example two different
    forks both called "agent"). To keep them apart, the destination folder
    carries a short hash of the full URL, so distinct URLs never land in the
    same directory while the same URL reuses its existing clone.
    """
    if not re.match(r"^(https://|http://|git@)", url):
        raise ValueError(f"URL no válida: {url!r}")
    DIR_CLONES.mkdir(parents=True, exist_ok=True)
    nombre = url.rstrip("/").split("/")[-1].replace(".git", "")
    sufijo = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    destino = DIR_CLONES / f"{nombre}-{sufijo}"
    if destino.exists():
        return destino
    # GIT_TERMINAL_PROMPT=0 stops git from blocking on a credentials prompt if
    # the URL is private or mistyped; "--" keeps the URL from being read as an
    # option.
    entorno = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    subprocess.run(["git", "clone", "--depth", "1", "--", url, str(destino)],
                   check=True, capture_output=True, text=True, env=entorno)
    return destino


def ejecutar_motor(repo: Path, run_id: int, hilos: int = 4,
                   excluir: str = "") -> Path:
    """Run find_prompts on one repository and return the generated JSON."""
    orden = [sys.executable, "-m", "gen_prompts.find_prompts",
             "--run_id", str(run_id), "--repo_dir", str(repo),
             "--threads", str(hilos)]
    if excluir.strip():
        orden += ["--exclude-dirs", excluir.strip()]
    completado = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True)
    if completado.returncode != 0:
        # Surface the engine's own error instead of a bare exit code.
        detalle = (completado.stderr or completado.stdout or "").strip()
        ultimas = "\n".join(detalle.splitlines()[-3:])
        raise RuntimeError(ultimas or f"código de salida {completado.returncode}")
    return DIR_DATOS / f"repo_data_export_{run_id:03d}.json"


def localizar_linea(archivo: Path, fragmento: str) -> int | None:
    """Line where the captured snippet starts, if it can be located.

    The engine does not record positions, but the captured text is a literal
    slice of the file, so a direct search is enough to recover the line.
    """
    try:
        contenido = archivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    aguja = fragmento.strip()
    # The match must not be the prefix of a longer identifier: without this,
    # "repair_prompt = AGENTLESS_PROMPT" would match the line holding
    # "repair_prompt = AGENTLESS_PROMPT_TOOL_USE".
    patron = re.escape(aguja[:400]) + r"(?![A-Za-z0-9_])"
    encontrado = re.search(patron, contenido)
    if encontrado is None:
        encontrado = re.search(re.escape(aguja[:120]), contenido)
    if encontrado is None:
        return None
    return contenido.count("\n", 0, encontrado.start()) + 1


def commit_de(carpeta: Path) -> str:
    """Commit checked out in a repository, or '' if it cannot be read.

    Each detection carries the commit of the code it was found in, so a
    result can be traced back to the exact version that was analysed. The
    command-line CSV export records the same information.
    """
    try:
        completado = subprocess.run(
            ["git", "-C", str(carpeta), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True)
        return completado.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


def leer_detecciones(json_path: Path, repo: Path, nombre: str,
                     commit: str = "") -> list[dict]:
    """Flatten the engine output into one row per detection.

    The visible columns follow the same order as the command-line CSV export:
    repository, commit, file, line, heuristic and prompt.
    """
    datos = json.loads(json_path.read_text(encoding="utf-8"))
    filas: list[dict] = []
    for ruta_txt, heuristicas in datos.items():
        ruta = Path(ruta_txt)
        try:
            relativa = ruta.relative_to(repo)
        except ValueError:
            relativa = Path(ruta.name)
        for heuristica, capturas in heuristicas.items():
            if heuristica == "variables" or not capturas:
                continue
            for captura in capturas:
                texto = captura if isinstance(captura, str) else str(captura)
                filas.append({
                    "repositorio": nombre,
                    "commit": commit,
                    "archivo": str(relativa).replace("\\", "/"),
                    "linea": localizar_linea(ruta, texto),
                    "heuristica": heuristica,
                    "prompt": " ".join(texto.split()),
                    "_ruta_absoluta": str(ruta),
                    "_texto_original": texto,
                })
    return filas


def ventana_codigo(archivo: Path, linea: int, alcance: int = 1,
                   margen: int = 8) -> tuple[str, int]:
    """Return a window of the file covering the detection plus some context.

    `alcance` is how many lines the captured text spans: a long prompt must be
    shown whole, not clipped to a fixed number of lines around its first line.
    """
    lineas = archivo.read_text(encoding="utf-8", errors="replace").splitlines()
    ini = max(0, linea - 1 - margen)
    fin = min(len(lineas), linea - 1 + alcance + margen)
    trozo = []
    for i in range(ini, fin):
        dentro = linea <= (i + 1) < linea + alcance
        marca = ">>" if dentro else "  "
        trozo.append(f"{marca} {i + 1:>5} | {lineas[i]}")
    return "\n".join(trozo), ini + 1


# ---------------------------------------------------------------------------
# View 1: analysis
# ---------------------------------------------------------------------------

def pantalla_analisis() -> None:
    st.header("Análisis de repositorios")
    st.write("Selecciona qué analizar y pulsa el botón. Los resultados "
             "aparecerán en la pestaña siguiente.")

    modo = st.radio("Origen de los repositorios",
                    ["Carpeta local", "Lista de URLs de GitHub"],
                    horizontal=True)

    repos: list[tuple[str, Path]] = []

    if modo == "Carpeta local":
        ruta_txt = st.text_input(
            "Ruta de la carpeta",
            help="Puede ser un repositorio suelto o una carpeta que contenga "
                 "varios repositorios.")
        if ruta_txt:
            carpeta = Path(ruta_txt).expanduser()
            if not carpeta.is_dir():
                st.error("Esa carpeta no existe.")
            else:
                subdirs = [d for d in sorted(carpeta.iterdir())
                           if d.is_dir() and not d.name.startswith(".")]
                candidatos = [d for d in subdirs if es_repositorio(d)]

                if es_repositorio(carpeta) or not candidatos:
                    # A single repository, or a plain folder with no git
                    # metadata: analyse it as one unit.
                    repos = [(carpeta.name, carpeta)]
                    st.caption(f"Se analizará **{carpeta.name}** como un único "
                               f"repositorio ({contar_py(carpeta)} archivos .py).")
                else:
                    # Preselecting every repository fills the multiselect with
                    # tags and makes it unusable, so the common case (analyse
                    # everything) is a checkbox instead.
                    todos = st.checkbox(
                        f"Analizar los {len(candidatos)} repositorios",
                        value=True)
                    if todos:
                        repos = [(d.name, d) for d in candidatos]
                    else:
                        elegidos = st.multiselect(
                            "Repositorios a analizar",
                            [d.name for d in candidatos], default=[])
                        repos = [(d.name, d) for d in candidatos
                                 if d.name in elegidos]
    else:
        urls_txt = st.text_area("Una URL por línea", height=150,
                                placeholder="https://github.com/usuario/repo")
        urls = [u.strip() for u in urls_txt.splitlines() if u.strip()]
        repos = [(u.rstrip("/").split("/")[-1], Path("")) for u in urls]

    if repos:
        st.caption(f"{len(repos)} repositorio(s) preparado(s).")

    # The slider and the button live inside a form on purpose: in Streamlit any
    # widget change reruns the whole script, and doing that mid-analysis leaves
    # orphan worker pools behind, which can exhaust the machine's memory.
    # Widgets inside a form only take effect when the form is submitted.
    maximo = max(1, min(8, os.cpu_count() or 4))
    with st.form("lanzar_analisis"):
        hilos = st.slider("Hilos de análisis", 1, maximo, min(4, maximo),
                          help="Procesos en paralelo que usa el motor. Cada uno "
                               "consume memoria: subirlo no siempre acelera.")
        excluir = st.text_input(
            "Carpetas a excluir (opcional)",
            help="Nombres de carpeta separados por comas, además de las que el "
                 "motor ya ignora (venv, node_modules, testbed...). Útil cuando "
                 "un repositorio guarda copias de otros proyectos con un nombre "
                 "propio.")
        lanzar = st.form_submit_button("Analizar", type="primary",
                                       disabled=not repos)

    if lanzar:
        st.info("Análisis en curso. No toques los controles hasta que "
                "termine.")
        barra = st.progress(0.0)
        estado = st.empty()
        filas: list[dict] = []
        errores: list[str] = []

        for i, (nombre, carpeta) in enumerate(repos, start=1):
            estado.write(f"[{i}/{len(repos)}] {nombre}")
            try:
                if modo != "Carpeta local":
                    url = [u for u in urls if u.rstrip("/").endswith(nombre)][0]
                    carpeta = clonar(url)
                json_path = ejecutar_motor(carpeta, run_id=i, hilos=hilos,
                                           excluir=excluir)
                filas.extend(leer_detecciones(json_path, carpeta, nombre,
                                              commit_de(carpeta)))
            except subprocess.CalledProcessError as e:
                detalle = (e.stderr or "").strip().splitlines()
                errores.append(f"{nombre}: git falló ({detalle[-1] if detalle else e}"
                               ")")
            except Exception as e:                      # noqa: BLE001
                errores.append(f"{nombre}: {e}")
            barra.progress(i / len(repos))

        estado.empty()
        st.session_state["resultados"] = pd.DataFrame(filas)
        st.session_state["errores"] = errores

        if errores:
            st.warning("Algunos repositorios no se completaron:\n\n" +
                       "\n".join(f"- {e}" for e in errores))
        st.success(f"Análisis terminado: {len(filas)} prompts detectados en "
                   f"{len(repos) - len(errores)} repositorio(s).")


# ---------------------------------------------------------------------------
# View 2: results
# ---------------------------------------------------------------------------

def pantalla_resultados() -> None:
    st.header("Prompts detectados")
    df: pd.DataFrame | None = st.session_state.get("resultados")

    if df is None or df.empty:
        st.info("Todavía no hay resultados. Lanza un análisis en la otra pestaña.")
        return

    # Empty means "no filter": preselecting every value crowds the widget and
    # leaves no room to scroll through the tags.
    col1, col2 = st.columns(2)
    todos_repos = sorted(df["repositorio"].unique())
    todas_heur = sorted(df["heuristica"].unique())
    repos = col1.multiselect("Repositorio", todos_repos, default=[],
                             placeholder="Todos", key="filtro_repos")
    heur = col2.multiselect("Heurística", todas_heur, default=[],
                            placeholder="Todas", key="filtro_heur")
    vista = df[df["repositorio"].isin(repos or todos_repos)
               & df["heuristica"].isin(heur or todas_heur)]

    st.caption(f"{len(vista)} prompts en {vista['archivo'].nunique()} archivos.")
    tabla = vista.copy()
    # Keep line numbers as integers. A single detection without a line turns
    # the whole column into floats, so 184 would be shown as 184.0 both in the
    # table and in the downloaded CSV.
    tabla["linea"] = tabla["linea"].astype("Int64")
    # Since Streamlit 1.50 the table takes the full width by default; the old
    # use_container_width argument is deprecated and scheduled for removal.
    st.dataframe(
        tabla[["repositorio", "archivo", "linea", "heuristica", "prompt"]],
        hide_index=True)

    # The CSV carries every visible column plus the commit of each repository.
    st.download_button(
        "Descargar como CSV",
        tabla.drop(columns=["_ruta_absoluta", "_texto_original"]).to_csv(index=False),
        file_name="prompts.csv", mime="text/csv")

    st.divider()
    st.subheader("Ver en el código")

    if vista.empty:
        return

    etiquetas = [
        f"{f['repositorio']} · {f['archivo']}"
        + (f" · línea {int(f['linea'])}" if pd.notna(f["linea"]) else "")
        for _, f in vista.iterrows()
    ]
    elegido = st.selectbox("Prompt", range(len(etiquetas)),
                           format_func=lambda i: etiquetas[i])
    fila = vista.iloc[elegido]

    st.text_area("Texto capturado", fila["_texto_original"],
                 height=min(500, 90 + 18 * fila["_texto_original"].count("\n")))

    archivo = Path(fila["_ruta_absoluta"])
    if not archivo.exists():
        st.warning("El archivo ya no está disponible en disco.")
    elif pd.isna(fila["linea"]):
        st.warning("No se ha podido localizar la posición exacta en el archivo.")
    else:
        alcance = fila["_texto_original"].count("\n") + 1
        contexto = st.slider("Líneas de contexto", 0, 40, 8)
        codigo, _ = ventana_codigo(archivo, int(fila["linea"]),
                                   alcance=alcance, margen=contexto)
        st.code(codigo, language="text")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

st.title("promptset-extended")
st.caption("Detección de prompts en repositorios de código abierto")

pestana_analisis, pestana_resultados = st.tabs(["Análisis", "Resultados"])
with pestana_analisis:
    pantalla_analisis()
with pestana_resultados:
    pantalla_resultados()