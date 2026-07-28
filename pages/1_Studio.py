"""
Page 2: Studio. Three tabs -- Generate, My Videos, Pricing -- side by side.
"""

import os
import time

import streamlit as st

import billing
import ui
import video_engine as ve

st.set_page_config(page_title="Studio · AI Video Generator", page_icon="🎬", layout="centered")
ui.inject_theme()

# ---- Must be signed in to see this page ----
if "email" not in st.session_state:
    st.warning("Please sign in first.")
    if st.button("Go to sign-in"):
        st.switch_page("app.py")
    st.stop()

email = st.session_state.email

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
            st.query_params.clear()
        except Exception as e:
            st.error(f"Couldn't confirm payment: {e}")

is_generating = st.session_state.get("is_generating", False)
ui.slate_bar("REEL-001", status="live" if is_generating else "ready")

try:
    credits = billing.get_credits(email)
except Exception as e:
    st.error(f"Couldn't load your account: {e}")
    st.stop()

# ---- Session state: tracks the chain of clips for the current video ----
if "parts" not in st.session_state:
    st.session_state.parts = []
if "latest_video_url" not in st.session_state:
    st.session_state.latest_video_url = None

tab_generate, tab_my_videos, tab_pricing = st.tabs(["Generate", "My Videos", "Pricing"])

# ============================================================
# TAB: Generate
# ============================================================
with tab_generate:
    col_balance, _ = st.columns([2, 1])
    with col_balance:
        ui.credit_counter(credits)

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
            st.warning(f"You need at least {billing.COST_PER_CLIP_CREDITS} credits. See the Pricing tab.")

        if st.button("Generate video", type="primary", disabled=not prompt.strip() or not enough_credits):
            st.session_state.is_generating = True
            status_placeholder = st.empty()
            with st.spinner("Generating your video... this usually takes 1-3 minutes."):
                try:
                    video_url, detailed_prompt = ve.generate_first_clip(prompt, aspect_ratio, status_placeholder)
                    status_placeholder.empty()

                    billing.deduct_credits(email, billing.COST_PER_CLIP_CREDITS)

                    timestamp = int(time.time())
                    filepath = ve.download_video(video_url, f"video_{timestamp}_part1.mp4")

                    st.session_state.parts = [filepath]
                    st.session_state.latest_video_url = video_url
                    st.session_state.timestamp = timestamp
                    st.session_state.expanded_prompt = detailed_prompt
                    st.session_state.is_generating = False
                    st.rerun()
                except Exception as e:
                    status_placeholder.empty()
                    st.session_state.is_generating = False
                    st.error(f"Generation failed: {e}")

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
                st.session_state.is_generating = True
                status_placeholder = st.empty()
                with st.spinner("Extending your video..."):
                    try:
                        new_url, detailed_continuation = ve.extend_clip(
                            st.session_state.latest_video_url, continuation, status_placeholder
                        )
                        status_placeholder.empty()

                        billing.deduct_credits(email, billing.COST_PER_CLIP_CREDITS)

                        part_num = len(st.session_state.parts) + 1
                        filepath = ve.download_video(
                            new_url, f"video_{st.session_state.timestamp}_part{part_num}.mp4"
                        )
                        st.session_state.parts.append(filepath)
                        st.session_state.latest_video_url = new_url
                        st.session_state.expanded_prompt += f"\n\n[Extension {part_num - 1}]: {detailed_continuation}"
                        st.session_state.is_generating = False
                        st.rerun()
                    except Exception as e:
                        status_placeholder.empty()
                        st.session_state.is_generating = False
                        st.error(f"Extension failed: {e}")
            if not enough_credits:
                st.caption("Not enough credits to extend. See the Pricing tab.")

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
                    final_path = ve.concatenate_videos(
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

# ============================================================
# TAB: My Videos
# ============================================================
with tab_my_videos:
    ui.section_label("Archive")
    st.subheader("Your finished videos")

    if os.path.isdir(ve.OUTPUT_DIR):
        past_files = sorted(
            [f for f in os.listdir(ve.OUTPUT_DIR) if f.endswith("_final.mp4")], reverse=True
        )
    else:
        past_files = []

    if not past_files:
        st.caption("Nothing here yet -- finish a video in the Generate tab and it'll show up here.")
    else:
        for fname in past_files:
            filepath = os.path.join(ve.OUTPUT_DIR, fname)
            st.video(filepath)
            with open(filepath, "rb") as f:
                st.download_button("Download", data=f, file_name=fname, mime="video/mp4", key=f"dl_{fname}")
            ui.film_divider()

# ============================================================
# TAB: Pricing
# ============================================================
with tab_pricing:
    ui.section_label("Top up")
    st.subheader("Buy credits")
    st.caption(f"1 credit = ${billing.PRICE_PER_CREDIT:.2f}. Each clip (or extension) costs {billing.COST_PER_CLIP_CREDITS} credits.")

    ui.credit_counter(credits)
    st.write("")

    for pack_dollars in billing.PACK_OPTIONS_DOLLARS:
        pack_credits = billing.credits_for_dollars(pack_dollars)
        col_pack, col_action = st.columns([2, 1])
        with col_pack:
            st.write(f"**${pack_dollars}** → {pack_credits} credits (~{pack_credits // billing.COST_PER_CLIP_CREDITS} clips)")
        with col_action:
            if st.button(f"Buy ${pack_dollars}", key=f"pack_{pack_dollars}"):
                app_url = os.environ.get("APP_URL") or st.secrets.get("APP_URL", "http://localhost:8501")
                studio_url = app_url.rstrip("/") + "/Studio"
                checkout_url = billing.create_checkout_session(
                    email, pack_dollars, success_url=studio_url, cancel_url=studio_url
                )
                st.link_button("Complete payment on Stripe →", checkout_url)

# ---- Sidebar ----
st.sidebar.markdown('<div class="section-label">Crew</div>', unsafe_allow_html=True)
st.sidebar.text(f"Signed in as: {email}")
if st.sidebar.button("Switch account"):
    del st.session_state.email
    st.switch_page("app.py")
