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
app_password = billing.safe_secret("APP_PASSWORD")
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

# ---- Sign-up form (two steps: send a code, then verify it) ----
ui.film_divider()
ui.section_label("Slate in")

if "otp_sent_to" not in st.session_state:
    st.session_state.otp_sent_to = None

if not st.session_state.otp_sent_to:
    # ---- Step 1: collect email, send a verification code ----
    st.subheader("Enter your email to get started")
    st.caption("We'll send a 6-digit code to verify it's really you. New accounts start with 4 free credits.")

    email_input = st.text_input("Email", label_visibility="collapsed", placeholder="you@example.com")

    if st.button("Send code", type="primary", disabled=not email_input.strip()):
        email = email_input.strip().lower()
        try:
            billing.send_login_code(email)
            st.session_state.otp_sent_to = email
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't send verification code: {e}")

else:
    # ---- Step 2: verify the code ----
    st.subheader("Check your email")
    st.caption(f"We sent a 6-digit code to **{st.session_state.otp_sent_to}**. Enter it below.")

    code_input = st.text_input("Verification code", label_visibility="collapsed", placeholder="123456", max_chars=6)

    col_verify, col_back = st.columns(2)
    with col_verify:
        if st.button("Verify", type="primary", disabled=not code_input.strip()):
            email = st.session_state.otp_sent_to
            if billing.verify_login_code(email, code_input.strip()):
                try:
                    billing.get_or_create_user(email)  # creates the account if it doesn't exist yet
                    st.session_state.email = email
                    st.session_state.otp_sent_to = None
                    st.switch_page("pages/1_Studio.py")
                except Exception as e:
                    st.error(f"Couldn't create your account: {e}")
            else:
                st.error("That code didn't work. Check for typos, or it may have expired -- try sending a new one.")
    with col_back:
        if st.button("Use a different email"):
            st.session_state.otp_sent_to = None
            st.rerun()
