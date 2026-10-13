"""Public version of the interface: the file Streamlit Community Cloud runs.

It starts app.py in shared mode: only GitHub repositories can be analysed,
and each visitor's reviews stay in their own browser session.
"""

import os

os.environ.setdefault("PROMPTSET_SOLO_GITHUB", "1")

import app  # noqa: E402  (shared mode has to be on before app.py is loaded)

app.main()
