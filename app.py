"""
Streamlit UI for AI video generation with Claude-powered prompt expansion,
video extension/merging (Veo 3.1 + ffmpeg), and Stripe-backed credits.

SETUP:
1. pip install streamlit fal-client anthropic supabase stripe --break-system-packages
2. Install ffmpeg (system tool): brew install ffmpeg / sudo apt install ffmpeg
3. Set env vars (or Streamlit Cloud secrets):
       FAL_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY, STRIPE_SECRET_KEY
   Optional: APP_PASSWORD (extra access gate on top of the credit system)
4. See billing.py for the Supabase table setup SQL.
5. Run:  streamlit run app.py
"""

import os
import subprocess
import time
import urllib.request

import anthropic
import fal_client
import streamlit as st

import billing
import ui

# ---- Config ----
VIDEO_MODEL_ID = "fal-ai/veo3.1/fast"
EXTEND_MODEL_ID = "fal-ai/veo3.1/extend-video"
CLAUDE_MODEL_ID = "claude-haiku-4-5-20251001"
OUTPUT_DIR = "generated_videos"

PROMPT_EXPANSION_SYSTEM = """You are a prompt engineer for AI video generation models. \
Your job is to take a casual, brief description from a user and expand it into a \
detailed, well-structured prompt that a text-to-video model will interpret well.

Include, where relevant to the scene:
- Camera angle and movement (e.g. "slow dolly forward", "static wide shot", "handheld tracking shot")
- Lighting and mood (e.g. "golden hour side light", "soft overcast diffusion")
- Visual style (e.g. "cinematic, shallow depth of field", "clean commercial look")
- Pacing/action detail (what specifically happens, in what order, over the clip's duration)

Keep the subject and intent of the original prompt fully intact — you are adding \
useful cinematic detail, not changing what the user asked for. Respond with ONLY the \
expanded prompt text, nothing else — no preamble, no explanation, no quotation marks."""

CONTINUATION_EXPANSION_SYSTEM = """You are a prompt engineer for AI video generation \
models. You are given a casual description of what should happen NEXT in an existing \
video clip (the model already sees the last frame of the clip, so you do not need to \
re-describe the subject, setting, or style from scratch). Expand the description into \
a clear continuation prompt: what action happens next, how the camera moves (if it \
should change), and how the mood evolves, if at all. Keep it concise -- this is a \
short continuation, not a new scene. Respond with ONLY the expanded prompt text, \
nothing else -- no preamble, no explanation, no quotation marks."""


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
    "Describe a scene in plain words. Claude sharpens it into a cinematic prompt, Veo 3.1 shoots it — extend the take as many times as you like.",
)

# ---- Check core API keys up front ----
fal_key = os.environ.get("FAL_KEY") or st.secrets.get("FAL_KEY")
anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or st.secrets.get("ANTHROPIC_API_KEY")

if not fal_key or not anthropic_key:
    st.error("Missing FAL_KEY or ANTHROPIC_API_KEY. Set them as env vars or Streamlit secrets.")
    st.stop()

os.environ["FAL_KEY"] = fal_key
os.environ["ANTHROPIC_API_KEY"] = anthropic_key

# ---- Handle return from Stripe checkout (before anything else renders) ----
query_params = st.query_params
if "session_id" in query_params:
    session_id = query_params["session_id"]
    with st.spinner("Confirming your payment..."):
        try:
            new_balance = billing.verify_and_credit(session_id)
            if new_balance is not None:
                st.success(f"Payment confirmed! New balance: {new_balance} credits.")
            # Clear the query param so a page refresh doesn't re-trigger this
            st.query_params.clear()
        except Exception as e:
            st.error(f"Couldn't confirm payment: {e}")

# ---- Email gate (identifies the user for credit tracking) ----
if "email" not in st.session_state:
    ui.section_label("Slate in")
    st.subheader("Enter your email to get started")
    st.caption("Tracks your credit balance. New accounts start with 4 free credits (2 free clips).")
    email_input = st.text_input("Email", label_visibility="collapsed", placeholder="you@example.com")
    if st.button("Continue", disabled=not email_input.strip()):
        st.session_state.email = email_input.strip().lower()
        st.rerun()
    st.stop()

email = st.session_state.email

# ---- Show credit balance + buy more ----
try:
    credits = billing.get_credits(email)
except Exception as e:
    st.error(f"Couldn't load your account: {e}")
    st.stop()

col_balance, col_buy = st.columns([2, 1])
with col_balance:
    ui.credit_counter(credits)
with col_buy:
    st.write("")  # vertical alignment nudge
    with st.popover("Buy credits"):
        ui.section_label("Top up")
        st.caption(f"1 credit = ${billing.PRICE_PER_CREDIT:.2f}. Each clip costs {billing.COST_PER_CLIP_CREDITS} credits.")
        for pack_dollars in billing.PACK_OPTIONS_DOLLARS:
            pack_credits = billing.credits_for_dollars(pack_dollars)
            if st.button(f"${pack_dollars} → {pack_credits} credits", key=f"pack_{pack_dollars}"):
                app_url = os.environ.get("APP_URL") or st.secrets.get("APP_URL", "http://localhost:8501")
                checkout_url = billing.create_checkout_session(
                    email, pack_dollars, success_url=app_url, cancel_url=app_url
                )
                st.link_button("Complete payment on Stripe →", checkout_url)

ui.film_divider()

# ---- Session state: tracks the chain of clips for the current video ----
if "parts" not in st.session_state:
    st.session_state.parts = []
if "latest_video_url" not in st.session_state:
    st.session_state.latest_video_url = None


# ---- Core functions ----
def expand(system_prompt: str, casual_prompt: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=CLAUDE_MODEL_ID,
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": casual_prompt}],
    )
    return message.content[0].text.strip()


def generate_first_clip(casual_prompt: str, aspect_ratio: str, status_placeholder) -> tuple:
    status_placeholder.text("Expanding your prompt with Claude...")
    detailed_prompt = expand(PROMPT_EXPANSION_SYSTEM, casual_prompt)

    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                status_placeholder.text(f"Status: {log['message']}")

    result = fal_client.subscribe(
        VIDEO_MODEL_ID,
        arguments={"prompt": detailed_prompt, "aspect_ratio": aspect_ratio},
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    return result["video"]["url"], detailed_prompt


def extend_clip(previous_video_url: str, casual_continuation: str, status_placeholder) -> tuple:
    status_placeholder.text("Expanding your continuation with Claude...")
    detailed_continuation = expand(CONTINUATION_EXPANSION_SYSTEM, casual_continuation)

    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                status_placeholder.text(f"Status: {log['message']}")

    result = fal_client.subscribe(
        EXTEND_MODEL_ID,
        arguments={"video_url": previous_video_url, "prompt": detailed_continuation},
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    return result["video"]["url"], detailed_continuation


def download_video(url: str, filename: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    urllib.request.urlretrieve(url, filepath)
    return filepath


def concatenate_videos(filepaths: list, output_filename: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    list_path = os.path.join(OUTPUT_DIR, "_concat_list.txt")
    with open(list_path, "w") as f:
        for path in filepaths:
            abs_path = os.path.abspath(path).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")
    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path],
        capture_output=True, text=True,
    )
    os.remove(list_path)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")
    return output_path


# ---- UI: starting a new video ----
if not st.session_state.parts:
    ui.section_label("Scene 1")
    prompt = st.text_area(
        "Describe the video you want",
        placeholder="A slow cinematic drone shot flying over a misty mountain range at sunrise",
        height=100,
        label_visibility="collapsed",
    )
    aspect_ratio = st.selectbox("Aspect ratio", ["16:9", "9:16"], index=0)

    enough_credits = credits >= billing.COST_PER_CLIP_CREDITS
    if not enough_credits:
        st.warning(f"You need at least {billing.COST_PER_CLIP_CREDITS} credits to generate a clip. Buy more above.")

    if st.button("Generate video", type="primary", disabled=not prompt.strip() or not enough_credits):
        status_placeholder = st.empty()
        with st.spinner("Generating your video... this usually takes 1-3 minutes."):
            try:
                video_url, detailed_prompt = generate_first_clip(prompt, aspect_ratio, status_placeholder)
                status_placeholder.empty()

                # Only deduct credits AFTER successful generation
                billing.deduct_credits(email, billing.COST_PER_CLIP_CREDITS)

                timestamp = int(time.time())
                filepath = download_video(video_url, f"video_{timestamp}_part1.mp4")

                st.session_state.parts = [filepath]
                st.session_state.latest_video_url = video_url
                st.session_state.timestamp = timestamp
                st.session_state.expanded_prompt = detailed_prompt
                st.rerun()
            except Exception as e:
                status_placeholder.empty()
                st.error(f"Generation failed: {e}")

# ---- UI: video exists, show it + offer extend / finalize ----
else:
    st.success(f"{len(st.session_state.parts)} clip(s) generated so far (~{len(st.session_state.parts) * 8} sec)")

    with st.expander("Show expanded prompt(s) Claude used"):
        st.write(st.session_state.get("expanded_prompt", ""))

    st.video(st.session_state.parts[-1])

    ui.film_divider()
    ui.section_label(f"Take {len(st.session_state.parts) + 1}")
    st.subheader("Extend this video")
    st.caption(f"Costs {billing.COST_PER_CLIP_CREDITS} credits, same as a new clip.")
    continuation = st.text_area(
        "What happens next?",
        placeholder="The drone descends slowly toward a lake in the valley below",
        height=80,
        key="continuation_input",
    )

    col1, col2 = st.columns(2)
    with col1:
        enough_credits = credits >= billing.COST_PER_CLIP_CREDITS
        if st.button("Extend video", disabled=not continuation.strip() or not enough_credits):
            status_placeholder = st.empty()
            with st.spinner("Extending your video..."):
                try:
                    new_url, detailed_continuation = extend_clip(
                        st.session_state.latest_video_url, continuation, status_placeholder
                    )
                    status_placeholder.empty()

                    billing.deduct_credits(email, billing.COST_PER_CLIP_CREDITS)

                    part_num = len(st.session_state.parts) + 1
                    filepath = download_video(
                        new_url, f"video_{st.session_state.timestamp}_part{part_num}.mp4"
                    )
                    st.session_state.parts.append(filepath)
                    st.session_state.latest_video_url = new_url
                    st.session_state.expanded_prompt += f"\n\n[Extension {part_num - 1}]: {detailed_continuation}"
                    st.rerun()
                except Exception as e:
                    status_placeholder.empty()
                    st.error(f"Extension failed: {e}")
        if not enough_credits:
            st.caption("Not enough credits to extend. Buy more above.")

    with col2:
        if st.button("Start a new video"):
            st.session_state.parts = []
            st.session_state.latest_video_url = None
            st.rerun()

    ui.film_divider()
    ui.section_label("Wrap")
    st.subheader("Finalize")
    st.caption("Merge all clips into one final video file (free, no extra credits).")

    if st.button("Merge & finalize", type="primary"):
        with st.spinner("Merging clips with ffmpeg..."):
            try:
                final_path = concatenate_videos(
                    st.session_state.parts, f"video_{st.session_state.timestamp}_final.mp4"
                )
                st.success("Done! Here's your final video:")
                st.video(final_path)
                with open(final_path, "rb") as f:
                    st.download_button(
                        "Download final video",
                        data=f,
                        file_name=f"video_{st.session_state.timestamp}_final.mp4",
                        mime="video/mp4",
                    )
            except Exception as e:
                st.error(f"Merge failed: {e}. Is ffmpeg installed on this server?")

# ---- Sidebar ----
st.sidebar.markdown('<div class="section-label">Crew</div>', unsafe_allow_html=True)
st.sidebar.text(f"Signed in as: {email}")
if st.sidebar.button("Switch account"):
    del st.session_state.email
    st.rerun()

if os.path.isdir(OUTPUT_DIR):
    past_files = sorted(
        [f for f in os.listdir(OUTPUT_DIR) if f.endswith("_final.mp4")], reverse=True
    )
    if past_files:
        st.sidebar.markdown('<div class="section-label">Archive</div>', unsafe_allow_html=True)
        for fname in past_files[:10]:
            st.sidebar.text(fname)
