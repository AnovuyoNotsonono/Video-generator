"""
Minimal Streamlit UI for AI video generation via fal.ai's Veo 3 Fast API.

SETUP:
1. pip install streamlit fal-client --break-system-packages
2. export FAL_KEY="your-key-here"
3. Run:  streamlit run app.py
   (This opens a local browser tab — no terminal juggling needed after that.)
"""

import os
import time
import urllib.request

import fal_client
import streamlit as st

MODEL_ID = "fal-ai/veo3/fast"
OUTPUT_DIR = "generated_videos"

st.set_page_config(page_title="AI Video Generator", page_icon="🎬")
st.title("🎬 AI Video Generator")
st.caption("Text prompt in, video out — powered by Veo 3 Fast via fal.ai")

# ---- Check API key up front ----
# Works locally (env var) and on Streamlit Cloud (st.secrets)
fal_key = os.environ.get("FAL_KEY") or st.secrets.get("FAL_KEY")
if not fal_key:
    st.error(
        "FAL_KEY not set. Locally: run `export FAL_KEY=\"your-key-here\"` and restart. "
        "On Streamlit Cloud: add it under App settings > Secrets."
    )
    st.stop()
os.environ["FAL_KEY"] = fal_key  # fal_client reads from the environment

# ---- Input form ----
prompt = st.text_area(
    "Describe the video you want",
    placeholder="A slow cinematic drone shot flying over a misty mountain range at sunrise, golden light breaking through the clouds",
    height=100,
)

aspect_ratio = st.selectbox("Aspect ratio", ["16:9", "9:16"], index=0)

generate_clicked = st.button("Generate video", type="primary", disabled=not prompt.strip())

# ---- Generation logic ----
def generate_video(prompt: str, aspect_ratio: str, status_placeholder) -> str:
    def on_queue_update(update):
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                status_placeholder.text(f"Status: {log['message']}")

    result = fal_client.subscribe(
        MODEL_ID,
        arguments={"prompt": prompt, "aspect_ratio": aspect_ratio},
        with_logs=True,
        on_queue_update=on_queue_update,
    )
    return result["video"]["url"]


def download_video(url: str, filename: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    urllib.request.urlretrieve(url, filepath)
    return filepath


# ---- Run generation when button is clicked ----
if generate_clicked:
    status_placeholder = st.empty()
    with st.spinner("Generating your video... this usually takes 1-3 minutes."):
        try:
            video_url = generate_video(prompt, aspect_ratio, status_placeholder)
            status_placeholder.empty()

            timestamp = int(time.time())
            filepath = download_video(video_url, f"video_{timestamp}.mp4")

            st.success("Done!")
            st.video(filepath)

            with open(filepath, "rb") as f:
                st.download_button(
                    "Download video",
                    data=f,
                    file_name=f"video_{timestamp}.mp4",
                    mime="video/mp4",
                )

        except Exception as e:
            status_placeholder.empty()
            st.error(f"Generation failed: {e}")

# ---- Sidebar: show past generations from this session ----
if os.path.isdir(OUTPUT_DIR):
    past_files = sorted(os.listdir(OUTPUT_DIR), reverse=True)
    if past_files:
        st.sidebar.header("Past generations")
        for fname in past_files[:10]:
            st.sidebar.text(fname)
