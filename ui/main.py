"""CineVault Streamlit entry point.

uv run streamlit run ui/main.py      → http://localhost:8501
"""

import streamlit as st

from app.db.session import schema_versions

st.set_page_config(page_title="CineVault", page_icon="🎬", layout="wide")

# Same guard as the CLI: a clear message instead of a traceback.
try:
    current, head = schema_versions()
except Exception:  # noqa: BLE001 - any connection problem → friendly message
    st.error("Can't reach the database. Start it with: `docker compose up -d db`")
    st.stop()
if current != head:
    st.error(f"Database schema is at {current}, the code expects {head}. Run: "
             "`uv run alembic upgrade head`")  # fmt: skip
    st.stop()

pages = [
    st.Page("views/watchlist.py", title="Watchlist", icon="🎬", default=True),
]
st.navigation(pages).run()
