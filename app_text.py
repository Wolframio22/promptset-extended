"""Texts of the graphical interface in Spanish, English and Catalan.

Every visible string of app.py lives here, so adding a language means adding
one column to each entry. The heuristics keep their internal names in the
engine and in the exported files; the interface shows a readable name and a
short explanation instead.
"""

from __future__ import annotations

IDIOMAS = {"es": "Español", "en": "English", "ca": "Català"}
IDIOMA_POR_DEFECTO = "es"

TEXTOS: dict[str, dict[str, str]] = {
    # General -------------------------------------------------------------
    "titulo_app": {
        "es": "Extractor de prompts",
        "en": "Prompt extractor",
        "ca": "Extractor de prompts",
    },
    "subtitulo": {
        "es": "Detección de prompts en repositorios de código abierto",
        "en": "Prompt detection in open-source repositories",
        "ca": "Detecció de prompts en repositoris de codi obert",
    },
    "idioma": {"es": "Idioma", "en": "Language", "ca": "Idioma"},
    "vista_analisis": {"es": "1 · Analizar", "en": "1 · Analyse", "ca": "1 · Analitzar"},
    "vista_resultados": {"es": "2 · Resultados", "en": "2 · Results", "ca": "2 · Resultats"},
    "vista_revision": {"es": "3 · Revisar", "en": "3 · Review", "ca": "3 · Revisar"},
    "navegacion": {"es": "Paso", "en": "Step", "ca": "Pas"},
    "guia_titulo": {"es": "Guía rápida", "en": "Quick guide", "ca": "Guia ràpida"},
    "guia_texto": {
        "es": "1. **Analizar**: escribe la dirección de uno o varios repositorios de GitHub "
              "(o elige una carpeta) y pulsa *Analizar*.\n"
              "2. **Resultados**: mira el resumen, filtra la tabla y haz clic en una fila "
              "para revisarla.\n"
              "3. **Revisar**: comprueba cada detección en su código, indica si es un "
              "prompt, valórala y comenta. Todo se guarda solo.\n"
              "4. **Descarga** la tabla en CSV, con tu revisión incluida.",
        "en": "1. **Analyse**: type the address of one or more GitHub repositories "
              "(or pick a folder) and press *Analyse*.\n"
              "2. **Results**: look at the summary, filter the table and click a row "
              "to review it.\n"
              "3. **Review**: check each detection in its code, say whether it is a "
              "prompt, rate it and comment. Everything is saved automatically.\n"
              "4. **Download** the table as CSV, including your review.",
        "ca": "1. **Analitzar**: escriu l'adreça d'un o més repositoris de GitHub "
              "(o tria una carpeta) i prem *Analitzar*.\n"
              "2. **Resultats**: mira el resum, filtra la taula i fes clic en una fila "
              "per revisar-la.\n"
              "3. **Revisar**: comprova cada detecció en el seu codi, indica si és un "
              "prompt, valora-la i comenta. Tot es desa automàticament.\n"
              "4. **Descarrega** la taula en CSV, amb la revisió inclosa.",
    },
    "que_es_prompt": {
        "es": "Un **prompt** es el texto que el programa envía a un modelo de lenguaje para "
              "decirle qué hacer: instrucciones, plantillas, mensajes de sistema o "
              "descripciones de herramientas.",
        "en": "A **prompt** is the text a program sends to a language model to tell it what "
              "to do: instructions, templates, system messages or tool descriptions.",
        "ca": "Un **prompt** és el text que el programa envia a un model de llenguatge per "
              "dir-li què ha de fer: instruccions, plantilles, missatges de sistema o "
              "descripcions d'eines.",
    },
    "acerca": {
        "es": "Trabajo de Fin de Grado · FIB-UPC · [código fuente]({url})",
        "en": "Bachelor's thesis · FIB-UPC · [source code]({url})",
        "ca": "Treball de Fi de Grau · FIB-UPC · [codi font]({url})",
    },
    "revisiones_en": {
        "es": "Las revisiones se guardan en `{ruta}`.",
        "en": "Reviews are saved in `{ruta}`.",
        "ca": "Les revisions es desen a `{ruta}`.",
    },
    # Analysis ------------------------------------------------------------
    "analisis_titulo": {"es": "Analizar repositorios", "en": "Analyse repositories",
                        "ca": "Analitzar repositoris"},
    "analisis_intro": {
        "es": "Elige qué analizar y pulsa **Analizar**. Al terminar se abrirán los resultados.",
        "en": "Choose what to analyse and press **Analyse**. The results open when it finishes.",
        "ca": "Tria què vols analitzar i prem **Analitzar**. En acabar s'obriran els resultats.",
    },
    "origen": {"es": "Origen de los repositorios", "en": "Where the repositories are",
               "ca": "Origen dels repositoris"},
    "origen_urls": {"es": "GitHub", "en": "GitHub", "ca": "GitHub"},
    "origen_local": {"es": "Carpeta de mi ordenador", "en": "Folder on my computer",
                     "ca": "Carpeta del meu ordinador"},
    "urls_label": {
        "es": "Repositorios de GitHub, uno por línea",
        "en": "GitHub repositories, one per line",
        "ca": "Repositoris de GitHub, un per línia",
    },
    "urls_ayuda": {
        "es": "Vale la dirección completa (https://github.com/usuario/repositorio) "
              "o solo usuario/repositorio.",
        "en": "Either the full address (https://github.com/user/repository) "
              "or just user/repository.",
        "ca": "Val l'adreça completa (https://github.com/usuari/repositori) "
              "o només usuari/repositori.",
    },
    "ejemplo_boton": {"es": "Usar un ejemplo", "en": "Use an example", "ca": "Fer servir un exemple"},
    "ruta_label": {"es": "Ruta de la carpeta", "en": "Folder path", "ca": "Ruta de la carpeta"},
    "ruta_ayuda": {
        "es": "Puede ser un repositorio suelto o una carpeta que contenga varios repositorios.",
        "en": "It can be a single repository or a folder that holds several repositories.",
        "ca": "Pot ser un repositori sol o una carpeta que en contingui diversos.",
    },
    "carpeta_no_existe": {"es": "Esa carpeta no existe.", "en": "That folder does not exist.",
                          "ca": "Aquesta carpeta no existeix."},
    "un_repo": {
        "es": "Se analizará **{nombre}** como un único repositorio ({n} archivos .py).",
        "en": "**{nombre}** will be analysed as a single repository ({n} .py files).",
        "ca": "S'analitzarà **{nombre}** com un únic repositori ({n} fitxers .py).",
    },
    "analizar_todos": {"es": "Analizar los {n} repositorios", "en": "Analyse all {n} repositories",
                       "ca": "Analitzar els {n} repositoris"},
    "repos_elegir": {"es": "Repositorios a analizar", "en": "Repositories to analyse",
                     "ca": "Repositoris a analitzar"},
    "preparados": {"es": "Repositorios preparados: {n}.", "en": "Repositories ready: {n}.",
                   "ca": "Repositoris preparats: {n}."},
    "opciones_avanzadas": {"es": "Opciones avanzadas", "en": "Advanced options",
                           "ca": "Opcions avançades"},
    "hilos": {"es": "Hilos de análisis", "en": "Analysis threads", "ca": "Fils d'anàlisi"},
    "hilos_ayuda": {
        "es": "Procesos en paralelo que usa el motor. Cada uno consume memoria: subirlo no "
              "siempre acelera.",
        "en": "Parallel processes used by the engine. Each one uses memory: more is not "
              "always faster.",
        "ca": "Processos en paral·lel que fa servir el motor. Cadascun consumeix memòria: "
              "pujar-lo no sempre accelera.",
    },
    "excluir": {"es": "Carpetas a excluir (opcional)", "en": "Folders to skip (optional)",
                "ca": "Carpetes a excloure (opcional)"},
    "excluir_ayuda": {
        "es": "Nombres de carpeta separados por comas, además de las que el motor ya ignora "
              "(venv, node_modules, testbed...).",
        "en": "Folder names separated by commas, on top of the ones the engine already "
              "skips (venv, node_modules, testbed...).",
        "ca": "Noms de carpeta separats per comes, a més de les que el motor ja ignora "
              "(venv, node_modules, testbed...).",
    },
    "boton_analizar": {"es": "Analizar", "en": "Analyse", "ca": "Analitzar"},
    "nada_que_analizar": {
        "es": "Escribe al menos un repositorio o elige una carpeta.",
        "en": "Type at least one repository or choose a folder.",
        "ca": "Escriu almenys un repositori o tria una carpeta.",
    },
    "en_curso": {"es": "Analizando…", "en": "Analysing…", "ca": "Analitzant…"},
    "descargando": {"es": "Descargando {nombre}…", "en": "Downloading {nombre}…",
                    "ca": "Descarregant {nombre}…"},
    "analizando": {"es": "Buscando prompts en {nombre}…", "en": "Looking for prompts in {nombre}…",
                   "ca": "Cercant prompts a {nombre}…"},
    "repo_listo": {"es": "{nombre}: {n} prompts", "en": "{nombre}: {n} prompts",
                   "ca": "{nombre}: {n} prompts"},
    "error_git": {
        "es": "{nombre}: no se pudo descargar ({detalle}). ¿Es correcta la dirección y es público?",
        "en": "{nombre}: could not be downloaded ({detalle}). Is the address right and public?",
        "ca": "{nombre}: no s'ha pogut descarregar ({detalle}). L'adreça és correcta i pública?",
    },
    "error_url": {"es": "Dirección no válida: {url}", "en": "Invalid address: {url}",
                  "ca": "Adreça no vàlida: {url}"},
    "error_motor": {"es": "{nombre}: {detalle}", "en": "{nombre}: {detalle}",
                    "ca": "{nombre}: {detalle}"},
    "avisos": {"es": "Algunos repositorios no se completaron:",
               "en": "Some repositories could not be completed:",
               "ca": "Alguns repositoris no s'han completat:"},
    "terminado": {
        "es": "Análisis terminado: {n} prompts detectados en {r} repositorio(s).",
        "en": "Analysis finished: {n} prompts found in {r} repository(ies).",
        "ca": "Anàlisi acabada: {n} prompts detectats en {r} repositori(s).",
    },
    "estado_terminado": {"es": "Análisis terminado", "en": "Analysis finished",
                         "ca": "Anàlisi acabada"},
    "ver_resultados": {"es": "Ver los resultados", "en": "See the results", "ca": "Veure els resultats"},
    # Results -------------------------------------------------------------
    "resultados_titulo": {"es": "Resultados", "en": "Results", "ca": "Resultats"},
    "sin_resultados": {
        "es": "Todavía no hay resultados. Empieza por el paso 1 · Analizar.",
        "en": "There are no results yet. Start with step 1 · Analyse.",
        "ca": "Encara no hi ha resultats. Comença pel pas 1 · Analitzar.",
    },
    "m_prompts": {"es": "Prompts detectados", "en": "Prompts found", "ca": "Prompts detectats"},
    "m_archivos": {"es": "Archivos con prompts", "en": "Files with prompts",
                   "ca": "Fitxers amb prompts"},
    "m_repos": {"es": "Repositorios", "en": "Repositories", "ca": "Repositoris"},
    "m_revisados": {"es": "Revisados", "en": "Reviewed", "ca": "Revisats"},
    "resumen_titulo": {"es": "Resumen", "en": "Summary", "ca": "Resum"},
    "g_por_tipo": {"es": "Detecciones por tipo", "en": "Detections by type",
                   "ca": "Deteccions per tipus"},
    "g_por_archivo": {"es": "Archivos con más detecciones", "en": "Files with most detections",
                      "ca": "Fitxers amb més deteccions"},
    "g_revision": {"es": "Estado de la revisión", "en": "Review status", "ca": "Estat de la revisió"},
    "eje_detecciones": {"es": "Detecciones", "en": "Detections", "ca": "Deteccions"},
    "glosario_titulo": {
        "es": "¿Qué significa cada tipo de detección?",
        "en": "What does each type of detection mean?",
        "ca": "Què vol dir cada tipus de detecció?",
    },
    "filtro_repo": {"es": "Repositorio", "en": "Repository", "ca": "Repositori"},
    "filtro_tipo": {"es": "Tipo de detección", "en": "Type of detection", "ca": "Tipus de detecció"},
    "filtro_estado": {"es": "Revisión", "en": "Review", "ca": "Revisió"},
    "filtro_buscar": {"es": "Buscar", "en": "Search", "ca": "Cercar"},
    "filtro_buscar_ph": {"es": "texto o archivo: JSON, core/ai.py…",
                         "en": "text or file: JSON, core/ai.py…",
                         "ca": "text o fitxer: JSON, core/ai.py…"},
    "todos": {"es": "Todos", "en": "All", "ca": "Tots"},
    "n_filtrados": {"es": "{n} prompts en {f} archivos.", "en": "{n} prompts in {f} files.",
                    "ca": "{n} prompts en {f} fitxers."},
    "tabla_ayuda": {
        "es": "Haz clic en una fila para seleccionarla y revisarla.",
        "en": "Click a row to select it and review it.",
        "ca": "Fes clic en una fila per seleccionar-la i revisar-la.",
    },
    "revisar_seleccion": {"es": "Revisar la fila seleccionada", "en": "Review the selected row",
                          "ca": "Revisar la fila seleccionada"},
    "col_repositorio": {"es": "Repositorio", "en": "Repository", "ca": "Repositori"},
    "col_archivo": {"es": "Archivo", "en": "File", "ca": "Fitxer"},
    "col_linea": {"es": "Línea", "en": "Line", "ca": "Línia"},
    "col_tipo": {"es": "Tipo de detección", "en": "Type of detection", "ca": "Tipus de detecció"},
    "col_prompt": {"es": "Texto detectado", "en": "Detected text", "ca": "Text detectat"},
    "col_revision": {"es": "¿Es un prompt?", "en": "Is it a prompt?", "ca": "És un prompt?"},
    "col_valoracion": {"es": "Valoración", "en": "Rating", "ca": "Valoració"},
    "descargar": {"es": "Descargar CSV", "en": "Download CSV", "ca": "Descarregar CSV"},
    "descargar_ayuda": {
        "es": "Las filas filtradas, con la revisión (es prompt, valoración y comentario).",
        "en": "The filtered rows, with the review (is prompt, rating and comment).",
        "ca": "Les files filtrades, amb la revisió (és prompt, valoració i comentari).",
    },
    "descargar_confirmados": {
        "es": "Descargar solo los confirmados como prompt",
        "en": "Download only the confirmed prompts",
        "ca": "Descarregar només els confirmats com a prompt",
    },
    # Review --------------------------------------------------------------
    "revision_titulo": {"es": "Revisión de detecciones", "en": "Review of detections",
                        "ca": "Revisió de deteccions"},
    "revision_intro": {
        "es": "Comprueba la detección en su código e indica si es un prompt. La valoración "
              "y el comentario son opcionales. Todo se guarda automáticamente.",
        "en": "Check the detection in its code and say whether it is a prompt. The rating "
              "and the comment are optional. Everything is saved automatically.",
        "ca": "Comprova la detecció en el seu codi i indica si és un prompt. La valoració i "
              "el comentari són opcionals. Tot es desa automàticament.",
    },
    "progreso": {"es": "Revisadas {r} de {n}", "en": "{r} of {n} reviewed", "ca": "Revisades {r} de {n}"},
    "revision_filtrada": {
        "es": "Se revisan las {n} detecciones que deja el filtro de Resultados.",
        "en": "You are reviewing the {n} detections left by the filter in Results.",
        "ca": "Es revisen les {n} deteccions que deixa el filtre de Resultats.",
    },
    "posicion": {"es": "Detección {i} de {n}", "en": "Detection {i} of {n}", "ca": "Detecció {i} de {n}"},
    "anterior": {"es": "Anterior", "en": "Previous", "ca": "Anterior"},
    "siguiente": {"es": "Siguiente", "en": "Next", "ca": "Següent"},
    "siguiente_sin": {"es": "Siguiente sin revisar", "en": "Next unreviewed",
                      "ca": "Següent sense revisar"},
    "linea_n": {"es": "línea {n}", "en": "line {n}", "ca": "línia {n}"},
    "detectado_por": {"es": "Detectado por: **{tipo}**", "en": "Detected by: **{tipo}**",
                      "ca": "Detectat per: **{tipo}**"},
    "texto_capturado": {"es": "Texto detectado", "en": "Detected text", "ca": "Text detectat"},
    "codigo": {"es": "Código", "en": "Code", "ca": "Codi"},
    "contexto": {"es": "Líneas de contexto", "en": "Context lines", "ca": "Línies de context"},
    "abrir_github": {"es": "Abrir en GitHub", "en": "Open on GitHub", "ca": "Obrir a GitHub"},
    "archivo_no_disponible": {
        "es": "El archivo ya no está disponible en disco.",
        "en": "The file is no longer available on disk.",
        "ca": "El fitxer ja no és disponible al disc.",
    },
    "linea_desconocida": {
        "es": "No se ha podido localizar la posición exacta en el archivo.",
        "en": "The exact position in the file could not be found.",
        "ca": "No s'ha pogut localitzar la posició exacta al fitxer.",
    },
    "tu_revision": {"es": "Tu revisión", "en": "Your review", "ca": "La teva revisió"},
    "pregunta_prompt": {"es": "¿Es un prompt?", "en": "Is it a prompt?", "ca": "És un prompt?"},
    "op_si": {"es": "Sí", "en": "Yes", "ca": "Sí"},
    "op_no": {"es": "No", "en": "No", "ca": "No"},
    "op_dudoso": {"es": "Dudoso", "en": "Unsure", "ca": "Dubtós"},
    "sin_revisar": {"es": "Sin revisar", "en": "Not reviewed", "ca": "Sense revisar"},
    "valoracion": {"es": "Valoración del prompt", "en": "Rating of the prompt",
                   "ca": "Valoració del prompt"},
    "valoracion_ayuda": {
        "es": "De 1 a 5: claridad y calidad del texto como instrucción para el modelo.",
        "en": "From 1 to 5: how clear and well written the text is as an instruction.",
        "ca": "D'1 a 5: claredat i qualitat del text com a instrucció per al model.",
    },
    "comentario": {"es": "Comentario", "en": "Comment", "ca": "Comentari"},
    "comentario_ph": {"es": "Opcional", "en": "Optional", "ca": "Opcional"},
    "guardado": {"es": "Guardado", "en": "Saved", "ca": "Desat"},
    "todo_revisado": {
        "es": "Todas las detecciones están revisadas.",
        "en": "Every detection has been reviewed.",
        "ca": "Totes les deteccions estan revisades.",
    },
}

# Internal heuristic name -> (readable name, explanation) per language.
HEURISTICAS: dict[str, dict[str, tuple[str, str]]] = {
    "used_prompt_or_template_name": {
        "es": ("Variable con nombre de prompt",
               ("Se asigna un texto a una variable cuyo nombre indica que es un prompt "
                '(prompt, template, instruction…). Ejemplo: SYSTEM_PROMPT = "You are…".')),
        "en": ("Prompt-named variable",
               ("A text is assigned to a variable whose name says it is a prompt (prompt, "
                'template, instruction…). Example: SYSTEM_PROMPT = "You are…".')),
        "ca": ("Variable amb nom de prompt",
               ("S'assigna un text a una variable el nom de la qual indica que és un prompt "
                '(prompt, template, instruction…). Exemple: SYSTEM_PROMPT = "You are…".')),
    },
    "used_in_openai_call": {
        "es": ("Llamada a la API de OpenAI",
               ("Los argumentos de una llamada como client.chat.completions.create(...): ahí "
                "van los mensajes que se envían al modelo.")),
        "en": ("OpenAI API call",
               ("The arguments of a call such as client.chat.completions.create(...): they "
                "carry the messages sent to the model.")),
        "ca": ("Crida a l'API d'OpenAI",
               ("Els arguments d'una crida com client.chat.completions.create(...): hi van "
                "els missatges que s'envien al model.")),
    },
    "used_in_langchain_llm_call": {
        "es": ("Plantilla o mensaje de LangChain",
               ("Se crea una plantilla o un mensaje con LangChain: PromptTemplate, "
                "ChatPromptTemplate, SystemMessage, HumanMessage…")),
        "en": ("LangChain template or message",
               ("A template or a message is created with LangChain: PromptTemplate, "
                "ChatPromptTemplate, SystemMessage, HumanMessage…")),
        "ca": ("Plantilla o missatge de LangChain",
               ("Es crea una plantilla o un missatge amb LangChain: PromptTemplate, "
                "ChatPromptTemplate, SystemMessage, HumanMessage…")),
    },
    "used_chat_function": {
        "es": ("Llamada a chat() o summarize()",
               ("Una llamada a un método llamado chat o summarize, habitual en los clientes "
                "de modelos de lenguaje.")),
        "en": ("chat() or summarize() call",
               ("A call to a method named chat or summarize, common in language model "
                "clients.")),
        "ca": ("Crida a chat() o summarize()",
               ("Una crida a un mètode anomenat chat o summarize, habitual en els clients de "
                "models de llenguatge.")),
    },
    "used_langchain_tool": {
        "es": ("Herramienta declarada con @tool",
               ("El texto de documentación de una función marcada con @tool: el modelo lo lee"
                " para decidir cuándo usar la herramienta.")),
        "en": ("Tool declared with @tool",
               ("The docstring of a function marked with @tool: the model reads it to decide "
                "when to use the tool.")),
        "ca": ("Eina declarada amb @tool",
               ("El text de documentació d'una funció marcada amb @tool: el model el llegeix "
                "per decidir quan fer servir l'eina.")),
    },
    "used_langchain_tool_class": {
        "es": ("Herramienta declarada como clase",
               ("El atributo description de una clase que define una herramienta (hereda de "
                "BaseTool o similar).")),
        "en": ("Tool declared as a class",
               ("The description attribute of a class that defines a tool (inherits from "
                "BaseTool or similar).")),
        "ca": ("Eina declarada com a classe",
               ("L'atribut description d'una classe que defineix una eina (hereta de BaseTool"
                " o similar).")),
    },
    "find_from_file": {
        "es": ("Plantilla cargada desde archivo",
               ("Una llamada Template.from_file(...): el texto del prompt está en otro "
                "archivo.")),
        "en": ("Template loaded from a file",
               ("A Template.from_file(...) call: the text of the prompt is in another file.")),
        "ca": ("Plantilla carregada des d'un fitxer",
               ("Una crida Template.from_file(...): el text del prompt és en un altre fitxer.")),
    },
}


def texto(clave: str, idioma: str, **valores) -> str:
    """Text for a key in the given language, with its placeholders filled in."""
    entrada = TEXTOS[clave]
    plantilla = entrada.get(idioma) or entrada[IDIOMA_POR_DEFECTO]
    return plantilla.format(**valores) if valores else plantilla


def nombre_heuristica(interno: str, idioma: str) -> str:
    """Readable name of a heuristic; unknown names are shown as they are."""
    entrada = HEURISTICAS.get(interno)
    if entrada is None:
        return interno
    return (entrada.get(idioma) or entrada[IDIOMA_POR_DEFECTO])[0]


def descripcion_heuristica(interno: str, idioma: str) -> str:
    entrada = HEURISTICAS.get(interno)
    if entrada is None:
        return ""
    return (entrada.get(idioma) or entrada[IDIOMA_POR_DEFECTO])[1]
