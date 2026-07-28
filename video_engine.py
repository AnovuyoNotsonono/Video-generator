"""
Shared video generation logic: Claude prompt expansion, Veo 3.1 generation
and extension, and ffmpeg concatenation. Used by the Studio page.
"""

import os
import subprocess
import urllib.request

import anthropic
import fal_client

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
