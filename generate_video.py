"""
AI video generation script with Claude-powered prompt expansion and support
for chaining longer videos via Veo 3.1's extend-video endpoint.

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
  casual prompt -> Claude expands it -> Veo3.1 generates first clip (~8 sec)
  optionally: casual continuation -> Claude expands it -> Veo3.1 extends the clip
  (repeat extension up to ~20 times for up to ~148 seconds total)
"""

import os
import subprocess
import sys
import time
import urllib.request

import anthropic
import fal_client

# ---- Config ----
VIDEO_MODEL_ID = "fal-ai/veo3.1/fast"          # base text-to-video generation
EXTEND_MODEL_ID = "fal-ai/veo3.1/extend-video"  # continues an existing clip
CLAUDE_MODEL_ID = "claude-haiku-4-5-20251001"   # fast + cheap, good fit for prompt rewriting
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


def _expand(system_prompt: str, casual_prompt: str) -> str:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment
    message = client.messages.create(
        model=CLAUDE_MODEL_ID,
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": casual_prompt}],
    )
    return message.content[0].text.strip()


def expand_prompt(casual_prompt: str) -> str:
    """Expands a casual prompt into a detailed video-generation prompt."""
    return _expand(PROMPT_EXPANSION_SYSTEM, casual_prompt)


def expand_continuation(casual_continuation: str) -> str:
    """Expands a casual 'what happens next' description for an extend-video call."""
    return _expand(CONTINUATION_EXPANSION_SYSTEM, casual_continuation)


def on_queue_update(update):
    """Prints progress logs while a fal.ai job is running."""
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            print(f"  [status] {log['message']}")


def _check_keys():
    if not os.environ.get("FAL_KEY"):
        sys.exit("ERROR: FAL_KEY environment variable not set.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY environment variable not set.")


def generate_video(casual_prompt: str, aspect_ratio: str = "16:9") -> str:
    """
    Generates the FIRST clip: expands the prompt with Claude, then calls Veo3.1.
    Returns the video URL.
    """
    _check_keys()

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
    print(f"\nClip done! Video URL: {video_url}")
    return video_url


def continue_video(previous_video_url: str, casual_continuation: str) -> str:
    """
    Extends an existing clip: expands the continuation prompt with Claude,
    then calls Veo3.1's extend-video endpoint. Returns the new (extended) video URL.
    """
    _check_keys()

    print(f"Continuing from: {previous_video_url}")
    print(f"Continuation idea: {casual_continuation}")
    print("Expanding continuation prompt with Claude...")
    detailed_continuation = expand_continuation(casual_continuation)
    print(f"Expanded continuation: {detailed_continuation}\n")

    print(f"Submitting job to {EXTEND_MODEL_ID} ...")
    result = fal_client.subscribe(
        EXTEND_MODEL_ID,
        arguments={"video_url": previous_video_url, "prompt": detailed_continuation},
        with_logs=True,
        on_queue_update=on_queue_update,
    )

    video_url = result["video"]["url"]
    print(f"\nExtended! Video URL: {video_url}")
    return video_url


def download_video(url: str, filename: str) -> str:
    """Downloads a video locally."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    urllib.request.urlretrieve(url, filepath)
    print(f"Saved to: {filepath}")
    return filepath


def concatenate_videos(filepaths: list, output_filename: str) -> str:
    """
    Merges multiple video files into one using ffmpeg's concat demuxer.
    Requires ffmpeg to be installed and on your PATH:
        Mac:     brew install ffmpeg
        Ubuntu:  sudo apt install ffmpeg
        Windows: https://ffmpeg.org/download.html

    Since all clips come from the same extend-video chain (same codec,
    resolution, and frame rate), the fast "concat demuxer" method works
    without needing to re-encode anything.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    # ffmpeg's concat demuxer needs a text file listing the parts, in order
    list_path = os.path.join(OUTPUT_DIR, "_concat_list.txt")
    with open(list_path, "w") as f:
        for path in filepaths:
            # ffmpeg wants forward slashes and quoted paths in this list file
            abs_path = os.path.abspath(path).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")

    print(f"Merging {len(filepaths)} clips into {output_path} ...")
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",  # overwrite output if it already exists
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",  # no re-encoding needed, same source codec throughout
            output_path,
        ],
        capture_output=True,
        text=True,
    )

    os.remove(list_path)

    if result.returncode != 0:
        print("ffmpeg failed. Is it installed? (brew install ffmpeg / apt install ffmpeg)")
        print(result.stderr)
        sys.exit(1)

    print(f"Merged video saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    # --- First clip ---
    test_prompt = "a drone shot over some mountains at sunrise"
    video_url = generate_video(test_prompt, aspect_ratio="16:9")

    timestamp = int(time.time())
    part1_path = download_video(video_url, f"video_{timestamp}_part1.mp4")

    # --- Extend it by one more segment ---
    # Comment this whole block out if you just want a single ~8 second clip.
    continuation_prompt = "the drone descends slowly toward a lake in the valley below"
    extended_url = continue_video(video_url, continuation_prompt)
    part2_path = download_video(extended_url, f"video_{timestamp}_part2.mp4")

    # --- Merge both parts into one final video ---
    final_path = concatenate_videos(
        [part1_path, part2_path],
        f"video_{timestamp}_final.mp4",
    )
    print(f"\nFinal merged video: {final_path}")
