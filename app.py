"""
Graphical interface for promptset-extended.

Place this file at the repository root (next to the gen_prompts/ package)
and run:

    streamlit run app.py

Three steps, chosen at the top of the page:
  1. Analyse -> pick repositories (GitHub addresses or a local folder) and
                run the engine
  2. Results -> summary charts and the table of detected prompts, with
                filters and CSV export
  3. Review  -> go through the detections one by one in their code, mark
                whether each one is a prompt, rate it and comment it

The texts are in Spanish, English and Catalan (app_text.py). Reviews are
saved to data/revisiones.json, so they survive a restart and a new analysis
of the same code. In the public version (streamlit_app.py) each visitor's
reviews stay in their own browser session instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from app_text import (
    HEURISTICAS,
    IDIOMA_POR_DEFECTO,
    IDIOMAS,
    descripcion_heuristica,
    nombre_heuristica,
)
from app_text import texto as _texto

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent          # engine root (gen_prompts/)
DIR_CLONES = RAIZ / "workspace"                 # cloned repositories land here
DIR_DATOS = RAIZ / "data"                       # engine output directory
# The tests point this to a temporary file through the environment.
FICHERO_REVISIONES = Path(os.environ.get("PROMPTSET_REVISIONES", DIR_DATOS / "revisiones.json"))
URL_PROYECTO = "https://github.com/Wolframio22/promptset-extended"
URL_EJEMPLO = "https://github.com/TheR1D/shell_gpt"
# When the interface is shared with other people (the public version in
# streamlit_app.py, or a tunnel in a remote user session),
# PROMPTSET_SOLO_GITHUB=1 hides the local folder option, so nobody can browse
# the files of this computer, and keeps each visitor's reviews in their own
# browser session instead of the shared file.
SOLO_GITHUB = os.environ.get("PROMPTSET_SOLO_GITHUB", "") not in ("", "0")
AZUL = "#2a78d6"                                # single-series colour of the charts
OPCIONES_REVISION = ("si", "no", "dudoso")
VISTAS = ("analisis", "resultados", "revision")
COLUMNAS = ["repositorio", "commit", "archivo", "linea", "heuristica", "prompt",
            "_ruta_absoluta", "_texto_original", "_remota", "_clave"]


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


def normalizar_url(entrada: str) -> str:
    """Accept 'user/repository' as a shorthand for a GitHub address."""
    limpia = entrada.strip()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", limpia):
        return f"https://github.com/{limpia}"
    return limpia


def nombre_repositorio(url: str) -> str:
    """'user/repository' for a GitHub address, the last segment otherwise."""
    ruta = url.rstrip("/").removesuffix(".git")
    partes = re.split(r"[/:]", ruta)
    if "github.com" in ruta and len(partes) >= 2:
        return f"{partes[-2]}/{partes[-1]}"
    return partes[-1]


class DireccionNoValida(ValueError):
    """The text typed is not a repository address that git can clone."""


def clonar(url: str) -> Path:
    """Clone a repository into the workspace and return its path.

    Two repositories can share the same final name (for example two different
    forks both called "agent"). To keep them apart, the destination folder
    carries a short hash of the full URL, so distinct URLs never land in the
    same directory while the same URL reuses its existing clone.
    """
    if not re.match(r"^(https://|http://|git@)", url):
        raise DireccionNoValida(url)
    DIR_CLONES.mkdir(parents=True, exist_ok=True)
    nombre = url.rstrip("/").split("/")[-1].removesuffix(".git")
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
    completado = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, check=False)
    if completado.returncode != 0:
        # Surface the engine's own error instead of a bare exit code.
        detalle = (completado.stderr or completado.stdout or "").strip()
        ultimas = "\n".join(detalle.splitlines()[-3:])
        raise RuntimeError(ultimas or f"exit code {completado.returncode}")
    return DIR_DATOS / f"repo_data_export_{run_id:03d}.json"


def localizar_linea(archivo: Path, fragmento: str, ocurrencia: int = 1) -> int | None:
    """Line where the captured snippet starts, if it can be located.

    The engine does not record positions, but the captured text is a literal
    slice of the file, so a direct search is enough to recover the line. When
    the same text is captured several times in a file, `ocurrencia` says which
    of its appearances this one is (the engine reports them in source order).
    """
    try:
        contenido = archivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    aguja = fragmento.strip()
    # The match must not be the prefix of a longer identifier: without this,
    # "repair_prompt = AGENTLESS_PROMPT" would match the line holding
    # "repair_prompt = AGENTLESS_PROMPT_TOOL_USE".
    for patron in (re.escape(aguja[:400]) + r"(?![A-Za-z0-9_])", re.escape(aguja[:120])):
        encontrados = list(re.finditer(patron, contenido))
        if encontrados:
            elegido = encontrados[min(ocurrencia, len(encontrados)) - 1]
            return contenido.count("\n", 0, elegido.start()) + 1
    return None


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


def url_remota(carpeta: Path) -> str:
    """Web address of the 'origin' remote when it is on GitHub, or ''."""
    try:
        completado = subprocess.run(
            ["git", "-C", str(carpeta), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, OSError):
        return ""
    remota = completado.stdout.strip()
    ssh = re.match(r"git@github\.com:(.+)", remota)
    if ssh:
        remota = "https://github.com/" + ssh.group(1)
    # Never show credentials that may be embedded in the address.
    remota = re.sub(r"^https://[^@/]+@github\.com", "https://github.com", remota)
    remota = remota.removesuffix(".git").rstrip("/")
    return remota if remota.startswith("https://github.com/") else ""


def enlace_github(remota: str, commit: str, archivo: str, linea) -> str:
    """Link to the exact line of the analysed commit, or '' when not on GitHub."""
    if not remota:
        return ""
    enlace = f"{remota}/blob/{commit or 'HEAD'}/{archivo}"
    if linea is not None and not pd.isna(linea):
        enlace += f"#L{int(linea)}"
    return enlace


def clave_deteccion(repositorio: str, commit: str, archivo: str, heuristica: str,
                    texto: str) -> str:
    """Stable identifier of a detection, used to store its review.

    It depends on the code that was analysed, not on the order of the
    results, so a review is found again after a new analysis of the same
    commit.
    """
    huella = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]
    return "|".join([repositorio, commit or "", archivo, heuristica, huella])


def leer_detecciones(json_path: Path, repo: Path, nombre: str,
                     commit: str = "", remota: str = "") -> list[dict]:
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
        archivo = str(relativa).replace("\\", "/")
        for heuristica, capturas in heuristicas.items():
            if heuristica == "variables" or not capturas:
                continue
            vistas: dict[str, int] = {}
            for captura in capturas:
                texto = captura if isinstance(captura, str) else str(captura)
                # Identical captures in one file (a repeated message, for
                # example) are told apart by their order of appearance.
                vistas[texto] = vistas.get(texto, 0) + 1
                clave = clave_deteccion(nombre, commit, archivo, heuristica, texto)
                if vistas[texto] > 1:
                    clave += f"#{vistas[texto]}"
                filas.append({
                    "repositorio": nombre,
                    "commit": commit,
                    "archivo": archivo,
                    "linea": localizar_linea(ruta, texto, vistas[texto]),
                    "heuristica": heuristica,
                    "prompt": " ".join(texto.split()),
                    "_ruta_absoluta": str(ruta),
                    "_texto_original": texto,
                    "_remota": remota,
                    "_clave": clave,
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


def cargar_revisiones(ruta: Path) -> dict:
    """Saved reviews, or an empty dict if the file is missing or damaged."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def guardar_revisiones(ruta: Path, revisiones: dict) -> None:
    """Write the reviews atomically, so a crash never leaves half a file."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".revisiones-",
                                            suffix=".json")
    with os.fdopen(descriptor, "w", encoding="utf-8") as f:
        json.dump(revisiones, f, ensure_ascii=False, indent=1)
    os.replace(temporal, ruta)


def revision_nueva(es_prompt, estrellas, comentario: str) -> dict | None:
    """Review record from the widget values; None when nothing was filled in.

    The rating widget returns 0-4 for one to five stars.
    """
    comentario = (comentario or "").strip()
    if es_prompt is None and estrellas is None and not comentario:
        return None
    return {
        "es_prompt": es_prompt or "",
        "valoracion": None if estrellas is None else int(estrellas) + 1,
        "comentario": comentario,
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def tabla_exportable(df: pd.DataFrame, revisiones: dict, idioma: str) -> pd.DataFrame:
    """Rows ready for the CSV download: detection, readable type and review."""
    salida = df[["repositorio", "commit", "archivo", "linea", "heuristica", "prompt"]].copy()
    salida["linea"] = salida["linea"].astype("Int64")
    salida.insert(5, "tipo_deteccion", df["heuristica"].map(lambda h: nombre_heuristica(h, idioma)))
    guardadas = df["_clave"].map(lambda k: revisiones.get(k, {}))
    salida["es_prompt"] = guardadas.map(lambda r: r.get("es_prompt", ""))
    salida["valoracion"] = guardadas.map(lambda r: r.get("valoracion")).astype("Int64")
    salida["comentario"] = guardadas.map(lambda r: r.get("comentario", ""))
    return salida


def grafico_barras(datos: pd.DataFrame, etiqueta: str, valor: str, titulo_eje: str):
    """Horizontal bars, one colour, sorted, with the value at the tip."""
    base = alt.Chart(datos).encode(
        y=alt.Y(f"{etiqueta}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
        x=alt.X(f"{valor}:Q", title=titulo_eje, axis=alt.Axis(tickMinStep=1, format="d")),
        tooltip=[alt.Tooltip(f"{etiqueta}:N", title=" "),
                 alt.Tooltip(f"{valor}:Q", title=titulo_eje)],
    )
    barras = base.mark_bar(color=AZUL, cornerRadiusEnd=4, size=16)
    valores = base.mark_text(align="left", dx=4).encode(text=f"{valor}:Q")
    return barras + valores


def acortar(texto: str, maximo: int = 52) -> str:
    """Keep the end of a long label: in a path the file name matters most."""
    return texto if len(texto) <= maximo else "…" + texto[-(maximo - 1):]


def altura_grafico(filas: int) -> int:
    """Pixels for a bar chart: one 30 px band per bar plus the axis."""
    return 30 * filas + 60


# ---------------------------------------------------------------------------
# Interface helpers
# ---------------------------------------------------------------------------

def idioma() -> str:
    return st.session_state.get("idioma", IDIOMA_POR_DEFECTO)


def t(clave: str, **valores) -> str:
    return _texto(clave, idioma(), **valores)


def nombre_tipo(heuristica: str) -> str:
    return nombre_heuristica(heuristica, idioma())


def etiqueta_estado(valor, idioma_texto: str) -> str:
    claves = {"si": "op_si", "no": "op_no", "dudoso": "op_dudoso"}
    return _texto(claves.get(valor, "sin_revisar"), idioma_texto)


def estado_legible(valor) -> str:
    return etiqueta_estado(valor, idioma())


# Widgets keep their format_func and may call it outside the script run
# (Streamlit's AppTest does), so the functions passed to them carry the
# language of the run in which they were created.

def formato_vista(idioma_texto: str):
    return lambda vista: _texto(f"vista_{vista}", idioma_texto)


def formato_origen(idioma_texto: str):
    return lambda modo: _texto("origen_urls" if modo == "urls" else "origen_local", idioma_texto)


def formato_tipo(idioma_texto: str):
    return lambda heuristica: nombre_heuristica(heuristica, idioma_texto)


def formato_estado(idioma_texto: str):
    return lambda valor: etiqueta_estado(valor, idioma_texto)


def ir_a(vista: str, clave: str | None = None) -> None:
    """Change step on the next run (a widget's value cannot change mid-run)."""
    st.session_state["_ir_a"] = vista
    if clave is not None:
        st.session_state["actual"] = clave


def poner_ejemplo() -> None:
    st.session_state["urls_txt"] = URL_EJEMPLO


@st.cache_resource(show_spinner="Preparando el analizador de Python / Preparing the Python analyser…")
def preparar_gramatica() -> None:
    """Download and compile the Tree-sitter grammar if it is missing.

    A new installation, such as the public version on Streamlit Community
    Cloud, only has the code of the repository. The commands are the ones in
    the README and in the continuous integration. Thanks to the cache, this
    runs only once, however many people open the page.
    """
    if (RAIZ / "build" / "my-languages.so").exists():
        return
    if not (RAIZ / "tree-sitter-python").exists():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", "v0.20.0",
                        "https://github.com/tree-sitter/tree-sitter-python"],
                       cwd=RAIZ, check=True)
    (RAIZ / "build").mkdir(exist_ok=True)
    # As in the continuous integration, the distutils of the standard library
    # is used: the copy bundled with recent setuptools links the grammar wrongly.
    subprocess.run([sys.executable, "-c", "from tree_sitter import Language; "
                    "Language.build_library('build/my-languages.so', ['tree-sitter-python'])"],
                   cwd=RAIZ, check=True, env={**os.environ, "SETUPTOOLS_USE_DISTUTILS": "stdlib"})


@st.cache_resource
def cerrojo_motor() -> threading.Lock:
    """One analysis at a time for everybody using this copy of the interface.

    Two analyses of the same repository would share its clone and the
    engine's working files, so the second one waits for the first to finish.
    """
    return threading.Lock()


# ---------------------------------------------------------------------------
# Sidebar and navigation
# ---------------------------------------------------------------------------

def barra_lateral() -> None:
    with st.sidebar:
        # The label does not change with the language, so the selector keeps
        # its state when the language changes.
        st.selectbox("Idioma · Language", list(IDIOMAS), format_func=IDIOMAS.get, key="idioma")
        with st.expander(t("guia_titulo"), expanded=True):
            st.markdown(t("guia_texto"))
            st.caption(t("que_es_prompt"))
        if not SOLO_GITHUB:
            ruta = FICHERO_REVISIONES
            if ruta.is_relative_to(RAIZ):
                ruta = ruta.relative_to(RAIZ)
            st.caption(t("revisiones_en", ruta=ruta.as_posix()))
        st.caption(t("acerca", url=URL_PROYECTO))


def navegacion() -> str:
    pendiente = st.session_state.pop("_ir_a", None)
    if pendiente in VISTAS:
        st.session_state["vista"] = pendiente
    if st.session_state.get("vista") not in VISTAS:
        st.session_state["vista"] = st.session_state.get("_vista_ultima", "analisis")
    elegida = st.segmented_control("vista", VISTAS, format_func=formato_vista(idioma()),
                                   key="vista", label_visibility="collapsed")
    if elegida is None:
        # Clicking the selected step again clears the control: stay where we were.
        elegida = st.session_state.get("_vista_ultima", "analisis")
        st.session_state["_ir_a"] = elegida
        st.rerun()
    st.session_state["_vista_ultima"] = elegida
    return elegida


# ---------------------------------------------------------------------------
# Step 1: analysis
# ---------------------------------------------------------------------------

def pantalla_analisis() -> None:
    st.header(t("analisis_titulo"))
    st.write(t("analisis_intro"))

    origenes = ["urls"] if SOLO_GITHUB else ["urls", "local"]
    modo = st.radio(t("origen"), origenes, horizontal=True, key="origen",
                    format_func=formato_origen(idioma()))

    repos: list[tuple[str, Path | None, str]] = []      # (name, folder, address)

    if modo == "local":
        ruta_txt = st.text_input(t("ruta_label"), help=t("ruta_ayuda"), key="ruta_local")
        if ruta_txt:
            carpeta = Path(ruta_txt).expanduser()
            if not carpeta.is_dir():
                st.error(t("carpeta_no_existe"))
            else:
                subdirs = [d for d in sorted(carpeta.iterdir())
                           if d.is_dir() and not d.name.startswith(".")]
                candidatos = [d for d in subdirs if es_repositorio(d)]
                if es_repositorio(carpeta) or not candidatos:
                    # A single repository, or a plain folder with no git
                    # metadata: analyse it as one unit.
                    repos = [(carpeta.name, carpeta, "")]
                    st.caption(t("un_repo", nombre=carpeta.name, n=contar_py(carpeta)))
                else:
                    # Preselecting every repository fills the multiselect with
                    # tags and makes it unusable, so the common case (analyse
                    # everything) is a checkbox instead.
                    if st.checkbox(t("analizar_todos", n=len(candidatos)), value=True):
                        repos = [(d.name, d, "") for d in candidatos]
                    else:
                        elegidos = st.multiselect(t("repos_elegir"), [d.name for d in candidatos])
                        repos = [(d.name, d, "") for d in candidatos if d.name in elegidos]
        if repos:
            st.caption(t("preparados", n=len(repos)))
    else:
        st.button(t("ejemplo_boton"), on_click=poner_ejemplo, icon=":material/lightbulb:")

    # The text, the options and the button live inside a form on purpose: in
    # Streamlit any widget change reruns the whole script, and doing that
    # mid-analysis leaves orphan worker pools behind, which can exhaust the
    # machine's memory. Widgets inside a form only take effect when the form
    # is submitted, and the addresses typed are sent together with the click.
    maximo = max(1, min(8, os.cpu_count() or 4))
    with st.form("lanzar_analisis"):
        if modo == "urls":
            urls_txt = st.text_area(t("urls_label"), key="urls_txt", height=110,
                                    placeholder="https://github.com/usuario/repo",
                                    help=t("urls_ayuda"))
        with st.expander(t("opciones_avanzadas")):
            hilos = st.slider(t("hilos"), 1, maximo, min(4, maximo), help=t("hilos_ayuda"))
            excluir = st.text_input(t("excluir"), help=t("excluir_ayuda"))
        lanzar = st.form_submit_button(t("boton_analizar"), type="primary",
                                       icon=":material/search:")

    if modo == "urls":
        for linea in urls_txt.splitlines():
            if linea.strip():
                url = normalizar_url(linea)
                repos.append((nombre_repositorio(url), None, url))

    if lanzar:
        if not repos:
            st.warning(t("nada_que_analizar"))
        else:
            ejecutar_analisis(repos, hilos, excluir)

    errores = st.session_state.get("errores")
    if errores and st.session_state.get("resultados") is not None:
        st.warning(t("avisos") + "\n\n" + "\n".join(f"- {e}" for e in errores))
        st.button(t("ver_resultados"), on_click=ir_a, args=("resultados",), type="primary")


def ejecutar_analisis(repos, hilos: int, excluir: str) -> None:
    filas: list[dict] = []
    errores: list[str] = []
    with st.status(t("en_curso"), expanded=True) as estado, cerrojo_motor():
        for i, (nombre, carpeta, url) in enumerate(repos, start=1):
            try:
                if url:
                    st.write(t("descargando", nombre=nombre))
                    carpeta = clonar(url)
                st.write(t("analizando", nombre=nombre))
                json_path = ejecutar_motor(carpeta, run_id=i, hilos=hilos, excluir=excluir)
                nuevas = leer_detecciones(json_path, carpeta, nombre, commit_de(carpeta),
                                          url_remota(carpeta))
                filas.extend(nuevas)
                st.write(t("repo_listo", nombre=nombre, n=len(nuevas)))
            except DireccionNoValida:
                errores.append(t("error_url", url=url))
            except subprocess.CalledProcessError as e:
                detalle = (e.stderr or "").strip().splitlines()
                errores.append(t("error_git", nombre=nombre,
                                 detalle=detalle[-1] if detalle else e.returncode))
            except Exception as e:                      # noqa: BLE001
                errores.append(t("error_motor", nombre=nombre, detalle=e))
        estado.update(label=t("estado_terminado"), state="error" if errores else "complete",
                      expanded=bool(errores))

    st.session_state["resultados"] = pd.DataFrame(filas, columns=COLUMNAS)
    st.session_state["errores"] = errores
    st.session_state["aviso"] = t("terminado", n=len(filas), r=len(repos) - len(errores))
    for clave in ("actual", "claves_filtradas"):
        st.session_state.pop(clave, None)
    if not errores:
        ir_a("resultados")
        st.rerun()


# ---------------------------------------------------------------------------
# Step 2: results
# ---------------------------------------------------------------------------

def pantalla_resultados() -> None:
    st.header(t("resultados_titulo"))
    df: pd.DataFrame | None = st.session_state.get("resultados")
    if df is None or df.empty:
        aviso = st.session_state.pop("aviso", None)
        if aviso:
            st.success(aviso)
        st.info(t("sin_resultados"))
        return
    aviso = st.session_state.pop("aviso", None)
    if aviso:
        st.success(aviso)

    revisiones = st.session_state["revisiones"]
    estados = df["_clave"].map(lambda k: revisiones.get(k, {}).get("es_prompt", ""))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("m_prompts"), len(df))
    c2.metric(t("m_archivos"), df[["repositorio", "archivo"]].drop_duplicates().shape[0])
    c3.metric(t("m_repos"), df["repositorio"].nunique())
    c4.metric(t("m_revisados"), f"{int((estados != '').sum())} / {len(df)}")

    with st.expander(t("resumen_titulo"), expanded=True):
        g1, g2 = st.columns(2)
        por_tipo = (df["heuristica"].map(nombre_tipo).value_counts()
                    .rename_axis("tipo").reset_index(name="n"))
        g1.markdown(f"**{t('g_por_tipo')}**")
        g1.altair_chart(grafico_barras(por_tipo, "tipo", "n", t("eje_detecciones")),
                        height=altura_grafico(len(por_tipo)))
        # With a single repository its name adds nothing to each label.
        rutas = df["archivo"] if df["repositorio"].nunique() == 1 else (
            df["repositorio"].str.split("/").str[-1] + " · " + df["archivo"])
        por_archivo = (rutas.map(acortar).value_counts().head(8)
                       .rename_axis("archivo").reset_index(name="n"))
        g2.markdown(f"**{t('g_por_archivo')}**")
        g2.altair_chart(grafico_barras(por_archivo, "archivo", "n", t("eje_detecciones")),
                        height=altura_grafico(len(por_archivo)))

    with st.expander(t("glosario_titulo")):
        st.markdown("\n".join(
            f"- **{nombre_heuristica(h, idioma())}**: {descripcion_heuristica(h, idioma())}"
            for h in HEURISTICAS))

    # Empty means "no filter": preselecting every value crowds the widget and
    # leaves no room to scroll through the tags.
    f1, f2, f3, f4 = st.columns([1, 1, 1, 1.3])
    todos_repos = sorted(df["repositorio"].unique())
    todos_tipos = sorted(df["heuristica"].unique(), key=nombre_tipo)
    repos = f1.multiselect(t("filtro_repo"), todos_repos, placeholder=t("todos"),
                           key="filtro_repos")
    tipos = f2.multiselect(t("filtro_tipo"), todos_tipos, format_func=formato_tipo(idioma()),
                           placeholder=t("todos"), key="filtro_tipos")
    opciones_estado = ["", *OPCIONES_REVISION]
    elegidos = f3.multiselect(t("filtro_estado"), opciones_estado,
                              format_func=formato_estado(idioma()), placeholder=t("todos"),
                              key="filtro_estado")
    buscar = f4.text_input(t("filtro_buscar"), placeholder=t("filtro_buscar_ph"),
                           key="filtro_buscar")

    mascara = df["repositorio"].isin(repos or todos_repos) & df["heuristica"].isin(tipos or todos_tipos)
    if elegidos:
        mascara &= estados.isin(elegidos)
    if buscar.strip():
        # The search looks at the captured text and at the file path.
        buscado = buscar.strip()
        mascara &= (df["_texto_original"].str.contains(buscado, case=False, regex=False)
                    | df["archivo"].str.contains(buscado, case=False, regex=False))
    vista = df[mascara]
    st.session_state["claves_filtradas"] = list(dict.fromkeys(vista["_clave"]))

    st.caption(t("n_filtrados", n=len(vista),
                 f=vista[["repositorio", "archivo"]].drop_duplicates().shape[0])
               + " " + t("tabla_ayuda"))
    tabla = pd.DataFrame({
        "repositorio": vista["repositorio"],
        "archivo": vista["archivo"],
        # A single detection without a line turns the column into floats, so
        # 184 would be shown as 184.0: keep it as a nullable integer.
        "linea": vista["linea"].astype("Int64"),
        "tipo": vista["heuristica"].map(nombre_tipo),
        "prompt": vista["prompt"].str.slice(0, 300),
        "revision": vista["_clave"].map(
            lambda k: estado_legible(revisiones.get(k, {}).get("es_prompt", ""))),
        "valoracion": vista["_clave"].map(
            lambda k: revisiones.get(k, {}).get("valoracion")).astype("Int64"),
    })
    evento = st.dataframe(
        tabla, hide_index=True, key="tabla_resultados", on_select="rerun",
        selection_mode="single-row",
        column_config={
            "repositorio": st.column_config.TextColumn(t("col_repositorio")),
            "archivo": st.column_config.TextColumn(t("col_archivo")),
            "linea": st.column_config.NumberColumn(t("col_linea"), format="%d"),
            "tipo": st.column_config.TextColumn(t("col_tipo")),
            "prompt": st.column_config.TextColumn(t("col_prompt"), width="large"),
            "revision": st.column_config.TextColumn(t("col_revision")),
            "valoracion": st.column_config.NumberColumn(t("col_valoracion"), format="%d ★"),
        })
    seleccion = [p for p in evento.selection.rows if p < len(vista)] if evento else []
    b1, b2, b3 = st.columns([1.2, 1, 1.6])
    # Shown even with nothing selected, so the feature is visible from the start.
    b1.button(t("revisar_seleccion"), type="primary", icon=":material/rate_review:",
              disabled=not seleccion, help=t("tabla_ayuda"), on_click=ir_a,
              args=("revision", vista.iloc[seleccion[0]]["_clave"] if seleccion else None))

    exportable = tabla_exportable(vista, revisiones, idioma())
    b2.download_button(t("descargar"), exportable.to_csv(index=False), file_name="prompts.csv",
                       mime="text/csv", help=t("descargar_ayuda"), on_click="ignore",
                       icon=":material/download:")
    confirmados = exportable[exportable["es_prompt"] == "si"]
    b3.download_button(t("descargar_confirmados"), confirmados.to_csv(index=False),
                       file_name="prompts_confirmados.csv", mime="text/csv",
                       disabled=confirmados.empty, on_click="ignore")


# ---------------------------------------------------------------------------
# Step 3: review
# ---------------------------------------------------------------------------

def mover(claves: list[str], posicion: int) -> None:
    st.session_state["actual"] = claves[max(0, min(posicion, len(claves) - 1))]


def siguiente_sin_revisar(claves: list[str], desde: int) -> None:
    revisiones = st.session_state["revisiones"]
    orden = claves[desde + 1:] + claves[:desde + 1]
    for clave in orden:
        if not revisiones.get(clave, {}).get("es_prompt"):
            st.session_state["actual"] = clave
            return


def guardar_revision(clave: str, sufijo: str) -> None:
    revisiones = st.session_state["revisiones"]
    nueva = revision_nueva(st.session_state.get(f"rev_es_{sufijo}"),
                           st.session_state.get(f"rev_val_{sufijo}"),
                           st.session_state.get(f"rev_com_{sufijo}", ""))
    if nueva is None:
        revisiones.pop(clave, None)
    else:
        revisiones[clave] = nueva
    # In shared mode the reviews stay in the visitor's session only.
    if not SOLO_GITHUB:
        guardar_revisiones(FICHERO_REVISIONES, revisiones)
    st.session_state["_guardado"] = clave


def pantalla_revision() -> None:
    st.header(t("revision_titulo"))
    df: pd.DataFrame | None = st.session_state.get("resultados")
    if df is None or df.empty:
        st.info(t("sin_resultados"))
        return

    revisiones = st.session_state["revisiones"]
    todas = list(dict.fromkeys(df["_clave"]))
    filtradas = [k for k in st.session_state.get("claves_filtradas", []) if k in set(todas)]
    claves = filtradas or todas
    if st.session_state.get("actual") not in claves:
        pendientes = [k for k in claves if not revisiones.get(k, {}).get("es_prompt")]
        st.session_state["actual"] = (pendientes or claves)[0]
    actual = st.session_state["actual"]
    i = claves.index(actual)
    hechas = sum(1 for k in claves if revisiones.get(k, {}).get("es_prompt"))

    st.caption(t("revision_intro"))
    if len(claves) < len(todas):
        st.caption(t("revision_filtrada", n=len(claves)))
    st.progress(hechas / len(claves), text=t("progreso", r=hechas, n=len(claves)))
    if hechas == len(claves):
        st.success(t("todo_revisado"))

    n1, n2, n3, n4 = st.columns([1, 1, 1.4, 2])
    n1.button(t("anterior"), icon=":material/arrow_back:", on_click=mover, args=(claves, i - 1),
              disabled=i == 0, key="nav_anterior")
    n2.button(t("siguiente"), icon=":material/arrow_forward:", on_click=mover,
              args=(claves, i + 1), disabled=i == len(claves) - 1, key="nav_siguiente")
    n3.button(t("siguiente_sin"), icon=":material/skip_next:", on_click=siguiente_sin_revisar,
              args=(claves, i), disabled=hechas == len(claves), key="nav_sin")
    n4.markdown(t("posicion", i=i + 1, n=len(claves)))

    fila = df[df["_clave"] == actual].iloc[0]
    texto_original = fila["_texto_original"]
    izquierda, derecha = st.columns([5, 2], gap="large")

    with izquierda:
        titulo = f"{fila['repositorio']} · `{fila['archivo']}`"
        if pd.notna(fila["linea"]):
            titulo += " · " + t("linea_n", n=int(fila["linea"]))
        st.markdown(f"#### {titulo}")
        st.markdown(t("detectado_por", tipo=nombre_tipo(fila["heuristica"])),
                    help=descripcion_heuristica(fila["heuristica"], idioma()))

        archivo = Path(fila["_ruta_absoluta"])
        if not archivo.exists():
            st.warning(t("archivo_no_disponible"))
        elif pd.isna(fila["linea"]):
            st.warning(t("linea_desconocida"))
        else:
            alcance = texto_original.count("\n") + 1
            contexto = st.slider(t("contexto"), 0, 40, 8, key="contexto_codigo")
            codigo, _ = ventana_codigo(archivo, int(fila["linea"]), alcance=alcance,
                                       margen=contexto)
            st.code(codigo, language="python")
        enlace = enlace_github(fila["_remota"], fila["commit"], fila["archivo"], fila["linea"])
        if enlace:
            st.link_button(t("abrir_github"), enlace, icon=":material/open_in_new:")
        with st.expander(t("texto_capturado")):
            st.code(texto_original, language="python", wrap_lines=True)

    with derecha:
        st.markdown(f"#### {t('tu_revision')}")
        # The language is part of the widget keys: after a change of language the
        # browser could otherwise send back the answer labelled in the old one.
        sufijo = f"{hashlib.sha1(actual.encode('utf-8')).hexdigest()[:10]}_{idioma()}"
        guardada = revisiones.get(actual, {})
        # Widgets start from the saved review the first time they are shown.
        st.session_state.setdefault(f"rev_es_{sufijo}", guardada.get("es_prompt") or None)
        estrellas = guardada.get("valoracion")
        st.session_state.setdefault(f"rev_val_{sufijo}", estrellas - 1 if estrellas else None)
        st.session_state.setdefault(f"rev_com_{sufijo}", guardada.get("comentario", ""))

        st.radio(t("pregunta_prompt"), OPCIONES_REVISION, format_func=formato_estado(idioma()),
                 horizontal=True, key=f"rev_es_{sufijo}", on_change=guardar_revision,
                 args=(actual, sufijo))
        st.markdown(t("valoracion"), help=t("valoracion_ayuda"))
        st.feedback("stars", key=f"rev_val_{sufijo}", on_change=guardar_revision,
                    args=(actual, sufijo))
        st.text_area(t("comentario"), key=f"rev_com_{sufijo}", placeholder=t("comentario_ph"),
                     height=100, on_change=guardar_revision, args=(actual, sufijo))
        if st.session_state.get("_guardado") == actual:
            st.caption(f":material/check: {t('guardado')}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Extractor de prompts · promptset-extended",
                       page_icon=":material/manage_search:",
                       layout="wide")

    # The engine runs as a subprocess with this same interpreter, so the
    # virtual environment must be active before launching Streamlit.
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        st.error("No se encuentra tree-sitter / tree-sitter is missing. Activa el entorno "
                 "virtual antes de lanzar la interfaz:\n\n"
                 "    source venv/bin/activate\n"
                 "    streamlit run app.py")
        st.stop()

    if st.session_state.get("idioma") not in IDIOMAS:
        st.session_state["idioma"] = IDIOMA_POR_DEFECTO
    if "revisiones" not in st.session_state:
        # In shared mode every visitor starts with no reviews.
        st.session_state["revisiones"] = {} if SOLO_GITHUB else cargar_revisiones(FICHERO_REVISIONES)
    preparar_gramatica()

    barra_lateral()
    # A plain name for the tool goes first, so anyone opening the page knows
    # what it does; the project name stays in the line below.
    st.title(t("titulo_app"))
    st.caption(f"promptset-extended · {t('subtitulo')}")
    vista = navegacion()
    {"analisis": pantalla_analisis, "resultados": pantalla_resultados,
     "revision": pantalla_revision}[vista]()


if __name__ == "__main__":
    main()
