"""
AI video generation script: Claude expands a casual prompt into a detailed
video-generation prompt, then fal.ai's Veo 3 Fast API generates the video.

SETUP:
1. Sign up at https://fal.ai and get an API key from your dashboard
2. Sign up at https://console.anthropic.com and get a Claude API key
3. Install dependencies:
       pip install fal-client anthropic --break-system-packages
4. Set both API keys as environment variables:
       export FAL_KEY="your-fal-key-here"
       export ANTHROPIC_API_KEY="your-claude-key-here"
5. Run:  python generate_video.py

PIPELINE:
  casual prompt -> Claude (expands into detailed cinematic prompt) -> Veo3 -> video
"""

import os
import sys
import time
import urllib.request

import anthropic
import fal_client

# ---- Config ----
VIDEO_MODEL_ID = "fal-ai/veo3/fast"
CLAUDE_MODEL_ID = "claude-haiku-4-5-20251001"  # fast + cheap, good fit for prompt rewriting
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


def expand_prompt(casual_prompt: str) -> str:
    """
    Uses Claude to expand a casual prompt into a detailed video-generation prompt.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

    message = client.messages.create(
        model=CLAUDE_MODEL_ID,
        max_tokens=300,
        system=PROMPT_EXPANSION_SYSTEM,
        messages=[{"role": "user", "content": casual_prompt}],
    )

    expanded = message.content[0].text.strip()
    return expanded


def on_queue_update(update):
    """Prints progress logs while the video generation job is running."""
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(f"  [status] {log['message']}")


def generate_video(casual_prompt: str, aspect_ratio: str = "16:9") -> str:
    """
    Full pipeline: expand the prompt with Claude, then generate the video with Veo3.
    Returns the URL of the generated video.
    """
    if not os.environ.get("FAL_KEY"):
        sys.exit("ERROR: FAL_KEY environment variable not set.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable not set.")

    print(f"Original prompt: {casual_prompt}")
    print("Expanding prompt with Claude...")
    detailed_prompt = expand_prompt(casual_prompt)
    print(f"Expanded prompt: {detailed_prompt}\n")

    print(f"Submitting job to {VIDEO_MODEL_ID} ...")
    result = fal_client.subscribe(
        VIDEO_MODEL_ID,
        arguments={"prompt": detailed_prompt, "aspect_ratio": aspect_ratio},
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
    # Edit this prompt to test different generations -- try something casual/brief,
    # since the whole point is Claude fleshes out the detail for you.
    test_prompt = "a drone shot over some mountains at sunrise"

    url = generate_video(test_prompt, aspect_ratio="16:9")

    timestamp = int(time.time())
    download_video(url, f"video_{timestamp}.mp4")
