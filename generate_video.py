"""
Minimal AI video generation script using fal.ai's Veo 3 Fast API.

SETUP:
1. Sign up at https://fal.ai and get an API key from your dashboard
2. Install the client:  pip install fal-client --break-system-packages
3. Set your API key as an environment variable:
       export FAL_KEY="your-key-here"
   (On Windows: set FAL_KEY=your-key-here)
4. Run:  python generate_video.py

Uses Veo 3 Fast (text-to-video) — roughly $0.10-0.15/sec, a good
prototyping-tier model with reliable, well-documented queue behavior.
"""

import os
import sys
import time
import urllib.request

import fal_client

# ---- Config ----
MODEL_ID = "fal-ai/veo3/fast"
OUTPUT_DIR = "generated_videos"


def on_queue_update(update):
    """Prints progress logs while the job is running."""
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(f"  [status] {log['message']}")


def generate_video(prompt: str, aspect_ratio: str = "16:9") -> str:
    """
    Submits a text-to-video generation job and waits for the result.
    Returns the URL of the generated video.
    """
    if not os.environ.get("FAL_KEY"):
        sys.exit("ERROR: FAL_KEY environment variable not set. See setup instructions at the top of this file.")

    print(f"Submitting job to {MODEL_ID} ...")
    print(f"Prompt: {prompt}")

    result = fal_client.subscribe(
        MODEL_ID,
        arguments={
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        },
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    video_url = result["video"]["url"]
    print(f"\nDone! Video URL: {video_url}")
    return video_url


def download_video(url: str, filename: str) -> str:
    """Downloads the generated video locally."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    urllib.request.urlretrieve(url, filepath)
    print(f"Saved to: {filepath}")
    return filepath


if __name__ == "__main__":
    # Edit this prompt to test different generations
    test_prompt = (
        "A slow cinematic drone shot flying over a misty mountain range at sunrise, "
        "golden light breaking through the clouds"
    )

    url = generate_video(test_prompt, aspect_ratio="16:9")

    timestamp = int(time.time())
    download_video(url, f"video_{timestamp}.mp4")
