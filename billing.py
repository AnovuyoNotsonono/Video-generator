"""
Billing module: tracks per-user credit balances (via Supabase) and handles
buying more credits (via Stripe Checkout).

SETUP:
1. Create a free project at https://supabase.com
2. In the SQL editor, run:

   create table users (
       email text primary key,
       credits integer not null default 4
   );

   create table processed_sessions (
       session_id text primary key,
       processed_at timestamp default now()
   );

   (New users start with 4 free credits = 2 free clips, to try before buying.)

3. Get your Project URL and "anon" public API key from
   Project Settings > API, set as env vars / Streamlit secrets:
       SUPABASE_URL
       SUPABASE_KEY

4. Create a Stripe account at https://stripe.com (test mode is fine to start).
   Get your secret key from Developers > API keys, set as:
       STRIPE_SECRET_KEY

5. pip install supabase stripe --break-system-packages

PRICING MODEL:
   1 credit = $1.20 (2x markup over ~$0.60 real cost per credit).
   Each clip generation OR extension costs 2 credits (~$2.40 to the user,
   against a real Veo3.1 cost of roughly $0.80-1.20 per clip).
   $15 minimum purchase nets roughly $6-7 profit after generation cost
   and Stripe fees -- new users get 4 free credits (2 free clips) as a
   trial, which costs you ~$2.40-4.80 in real generation cost per signup,
   worth treating as a deliberate acquisition cost, not an accident.
"""

import os

import stripe
from supabase import create_client

PRICE_PER_CREDIT = 1.20         # what a user pays per credit (2x markup over ~$0.60 real cost)
COST_PER_CLIP_CREDITS = 2       # each generation/extension call costs this many credits (~$2.40, against ~$1.20 real cost)
PACK_OPTIONS_DOLLARS = [15, 30, 60]  # $15 minimum nets ~$6-7 profit after generation cost + Stripe fees


def credits_for_dollars(dollars: float) -> int:
    """Converts a dollar amount into a whole number of credits (always rounds down,
    so you never accidentally give away a fraction of a credit for free)."""
    return int(dollars // PRICE_PER_CREDIT)


def _get_secret(name: str) -> str:
    value = os.environ.get(name) or _try_streamlit_secret(name)
    if not value:
        raise RuntimeError(f"Missing required secret: {name}")
    return value


def _try_streamlit_secret(name: str):
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        # Covers both "no secrets.toml file exists at all" (local dev without
        # one) and "key just isn't set" -- either way, treat as not found.
        return None


def safe_secret(name: str):
    """
    Public helper: checks an env var first, then Streamlit secrets (safely --
    won't crash if no secrets.toml exists at all, which happens often in
    local dev when you're using env vars instead). Returns None if not found
    anywhere, rather than raising.
    """
    return os.environ.get(name) or _try_streamlit_secret(name)


def _supabase_client():
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY")
    return create_client(url, key)


def _stripe_client():
    stripe.api_key = _get_secret("STRIPE_SECRET_KEY")
    return stripe


# ---- Email verification (self-built OTP, sent via Gmail SMTP) ----
# NOTE: Supabase's own magic-link/OTP email templates can no longer be
# customized on new free-tier projects (a platform restriction introduced
# June 2026), so this builds a lightweight code system instead: we generate
# the code, store it in our own `login_codes` table, and send it ourselves.
#
# Requires a Gmail "App Password" (not your real password):
#   Google Account > Security > 2-Step Verification > App Passwords
# Set as secrets:
#   GMAIL_ADDRESS       (the Gmail address sending the codes)
#   GMAIL_APP_PASSWORD  (the 16-character app password)

import random
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText


def send_login_code(email: str):
    """Generates a 6-digit code, stores it, and emails it to the user."""
    code = f"{random.randint(0, 999999):06d}"
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    client = _supabase_client()
    client.table("login_codes").insert({
        "email": email, "code": code, "expires_at": expires_at, "used": False,
    }).execute()

    gmail_address = _get_secret("GMAIL_ADDRESS")
    gmail_app_password = _get_secret("GMAIL_APP_PASSWORD")

    message = MIMEText(f"Your verification code is: {code}\n\nThis code expires in 10 minutes.")
    message["Subject"] = "Your verification code"
    message["From"] = gmail_address
    message["To"] = email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_app_password)
        server.sendmail(gmail_address, email, message.as_string())


def verify_login_code(email: str, code: str) -> bool:
    """Checks a 6-digit code against what we stored. Returns True if valid, unused, and unexpired."""
    client = _supabase_client()
    now = datetime.now(timezone.utc).isoformat()

    result = (
        client.table("login_codes")
        .select("*")
        .eq("email", email)
        .eq("code", code)
        .eq("used", False)
        .gte("expires_at", now)
        .execute()
    )

    if not result.data:
        return False

    # Mark it used so it can't be replayed
    row_id = result.data[0].get("id")
    if row_id:
        client.table("login_codes").update({"used": True}).eq("id", row_id).execute()
    else:
        # No id column (matches by email+code instead) -- still fine for a single-use code
        client.table("login_codes").update({"used": True}).eq("email", email).eq("code", code).execute()

    return True


# ---- Credit balance management ----

def get_or_create_user(email: str) -> int:
    """Returns the user's current credit balance, creating a new row (with
    4 free trial credits) if this email hasn't been seen before."""
    client = _supabase_client()
    result = client.table("users").select("*").eq("email", email).execute()

    if result.data:
        return result.data[0]["credits"]

    # New user: create with default free credits (table default handles this,
    # but we insert explicitly so we get the value back)
    insert_result = client.table("users").insert({"email": email, "credits": 4}).execute()
    return insert_result.data[0]["credits"]


def get_credits(email: str) -> int:
    client = _supabase_client()
    result = client.table("users").select("credits").eq("email", email).execute()
    if not result.data:
        return get_or_create_user(email)
    return result.data[0]["credits"]


def deduct_credits(email: str, amount: int) -> bool:
    """Attempts to deduct credits. Returns False if insufficient balance."""
    client = _supabase_client()
    current = get_credits(email)
    if current < amount:
        return False
    new_balance = current - amount
    client.table("users").update({"credits": new_balance}).eq("email", email).execute()
    return True


def add_credits(email: str, amount: int) -> int:
    """Adds credits (e.g. after a successful purchase). Returns new balance."""
    client = _supabase_client()
    current = get_credits(email)
    new_balance = current + amount
    client.table("users").update({"credits": new_balance}).eq("email", email).execute()
    return new_balance


# ---- Stripe checkout ----

def create_checkout_session(email: str, pack_dollars: int, success_url: str, cancel_url: str) -> str:
    """Creates a Stripe Checkout session for a credit pack purchase. Returns the checkout URL."""
    client = _stripe_client()
    credits_in_pack = credits_for_dollars(pack_dollars)

    session = client.checkout.Session.create(
        mode="payment",
        customer_email=email,
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"{credits_in_pack} video credits"},
                "unit_amount": pack_dollars * 100,  # Stripe expects cents
            },
            "quantity": 1,
        }],
        success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"email": email, "credits": str(credits_in_pack)},
    )
    return session.url


def verify_and_credit(session_id: str) -> int:
    """
    Verifies a completed Stripe checkout session and credits the user's
    account -- but only once per session_id, even if this function gets
    called multiple times (Streamlit reruns a lot).
    Returns the new credit balance, or None if already processed / invalid.
    """
    client = _supabase_client()
    stripe_client = _stripe_client()

    # Have we already processed this session? (prevents double-crediting on reruns)
    already = client.table("processed_sessions").select("session_id").eq("session_id", session_id).execute()
    if already.data:
        return None

    session = stripe_client.checkout.Session.retrieve(session_id)
    if session.payment_status != "paid":
        return None

    email = session.metadata["email"]
    credits_to_add = int(session.metadata["credits"])

    new_balance = add_credits(email, credits_to_add)

    # Mark this session as processed so a rerun can't credit it again
    client.table("processed_sessions").insert({"session_id": session_id}).execute()

    return new_balance
