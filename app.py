"""
Page 1: Sign-up gateway. Collects the user's email (creates their credit
account via billing.py), then sends them into the Studio page.

SETUP: see video_engine.py and billing.py for full setup instructions.
Run:  streamlit run app.py
"""

import os

import streamlit as st

import billing
import ui

st.set_page_config(page_title="AI Video Generator", page_icon="🎬", layout="centered")
ui.inject_theme()
ui.slate_bar("REEL-001")

# ---- Optional extra password gate (on top of the credit system) ----
app_password = os.environ.get("APP_PASSWORD") or st.secrets.get("APP_PASSWORD")
if app_password:
    entered = st.text_input("Enter access password", type="password")
    if entered != app_password:
        st.stop()

ui.hero(
    "SHOOT YOUR SHOT",
    "SHOT",
    "Describe a scene in plain words. Claude sharpens it into a cinematic prompt, "
    "Veo 3.1 shoots it — extend the take as many times as you like.",
)

# ---- Already signed in this session? Skip straight to the Studio ----
if "email" in st.session_state:
    st.success(f"Signed in as {st.session_state.email}")
    if st.button("Enter Studio →", type="primary"):
        st.switch_page("pages/1_Studio.py")
    if st.button("Switch account"):
        del st.session_state.email
        st.rerun()
    st.stop()

# ---- Sign-up form ----
ui.film_divider()
ui.section_label("Slate in")
st.subheader("Enter your email to get started")
st.caption("Tracks your credit balance. New accounts start with 4 free credits (2 free clips).")

email_input = st.text_input("Email", label_visibility="collapsed", placeholder="you@example.com")

if st.button("Continue", type="primary", disabled=not email_input.strip()):
    email = email_input.strip().lower()
    try:
        billing.get_or_create_user(email)  # creates the account if it doesn't exist yet
        st.session_state.email = email
        st.switch_page("pages/1_Studio.py")
    except Exception as e:
        st.error(f"Couldn't create your account: {e}")
