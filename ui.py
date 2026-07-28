"""
Visual theme for the AI Video Generator: a film-production identity
(slates, timecodes, film-strip perforations) instead of generic AI-tool
dark mode. Keeps all styling in one place so app.py stays readable.
"""

import streamlit as st

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Anton&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
    --ink: #15120F;
    --surface: #1F1A16;
    --line: #33291F;
    --tungsten: #D98E3B;
    --tally: #C1443B;
    --paper: #F3EDE2;
    --ash: #948B7E;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ---- Slate header bar (replaces generic st.title) ---- */
.slate-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 18px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.08em;
    color: var(--ash);
    text-transform: uppercase;
    margin-bottom: 28px;
}
.slate-bar span.status-ready { color: var(--tungsten); }
.slate-bar span.status-live { color: var(--tally); }

/* ---- Hero title ---- */
.hero-title {
    font-family: 'Anton', sans-serif;
    font-size: 52px;
    letter-spacing: 0.02em;
    color: var(--paper);
    line-height: 1;
    margin: 0 0 6px 0;
    text-transform: uppercase;
}
.hero-title span { color: var(--tungsten); }
.hero-sub {
    font-family: 'Inter', sans-serif;
    color: var(--ash);
    font-size: 15px;
    margin-bottom: 30px;
    max-width: 560px;
}

/* ---- Film-perforation divider (signature element) ---- */
.film-divider {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 32px 0;
}
.film-divider .line {
    flex: 1;
    height: 1px;
    background: var(--line);
}
.film-divider .holes {
    display: flex;
    gap: 5px;
}
.film-divider .holes span {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--line);
    display: inline-block;
}

/* ---- Credit counter (timecode-style, signature element) ---- */
.credit-box {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 14px 20px;
    display: inline-block;
}
.credit-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--ash);
    text-transform: uppercase;
    margin-bottom: 4px;
}
.credit-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 34px;
    font-weight: 500;
    color: var(--tungsten);
    letter-spacing: 0.02em;
}
.credit-value::before { content: "◐ "; font-size: 20px; opacity: 0.6; }

/* ---- Section labels ---- */
.section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--tungsten);
    margin-bottom: 2px;
}

/* ---- Buttons ---- */
.stButton > button {
    border-radius: 4px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    text-transform: uppercase !important;
    font-size: 13px !important;
    border: 1px solid var(--line) !important;
}
.stButton > button[kind="primary"] {
    background: var(--tungsten) !important;
    color: var(--ink) !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background: #C67F2E !important;
}

/* ---- Text areas / inputs ---- */
[data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 4px !important;
    color: var(--paper) !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stTextArea"] textarea:focus, [data-testid="stTextInput"] input:focus {
    border-color: var(--tungsten) !important;
    box-shadow: 0 0 0 1px var(--tungsten) !important;
}

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--line) !important;
}
</style>
"""


def inject_theme():
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def slate_bar(project_name: str, status: str = "ready"):
    """Film-slate style status bar, replaces a generic app title."""
    status_class = "status-live" if status == "live" else "status-ready"
    status_label = "ROLLING" if status == "live" else "READY"
    st.markdown(
        f"""<div class="slate-bar">
            <span>PROJECT · {project_name}</span>
            <span class="{status_class}">● {status_label}</span>
        </div>""",
        unsafe_allow_html=True,
    )


def hero(title: str, accent_word: str, subtitle: str):
    """Big display headline with one word in the accent color."""
    title_html = title.replace(accent_word, f"<span>{accent_word}</span>")
    st.markdown(
        f"""<div class="hero-title">{title_html}</div>
            <div class="hero-sub">{subtitle}</div>""",
        unsafe_allow_html=True,
    )


def film_divider():
    """Signature perforation-style divider, replaces st.divider()."""
    st.markdown(
        """<div class="film-divider">
            <div class="holes"><span></span><span></span><span></span></div>
            <div class="line"></div>
            <div class="holes"><span></span><span></span><span></span></div>
        </div>""",
        unsafe_allow_html=True,
    )


def credit_counter(value: int):
    """Timecode-style credit balance display."""
    st.markdown(
        f"""<div class="credit-box">
            <div class="credit-label">Credits remaining</div>
            <div class="credit-value">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def section_label(text: str):
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)
