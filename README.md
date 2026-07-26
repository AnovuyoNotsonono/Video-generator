# AI Video Generator

A minimal web app for generating short AI videos from text prompts, built with Streamlit and [fal.ai](https://fal.ai)'s Veo 3 Fast API.

Type a description, get a short video back — no editing software, no manual generation, just prompt in, video out.

![screenshot placeholder](docs/screenshot.png)

## Features

- Text-to-video generation via Veo 3 Fast
- Simple web UI — no command line needed after setup
- Choose between landscape (16:9) and portrait (9:16) aspect ratios
- Live generation status while your video renders
- Download generated videos directly from the browser
- Sidebar history of past generations

## Tech stack

- [Streamlit](https://streamlit.io) — web UI
- [fal.ai](https://fal.ai) — video generation API (Veo 3 Fast)
- Python 3.13

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/video-generator.git
cd video-generator
```

### 2. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Get a fal.ai API key

Sign up at [fal.ai](https://fal.ai) and create an API key from your dashboard. Copy the full key, including the colon (`key_id:key_secret`).

### 4. Set your API key

```bash
export FAL_KEY="your_key_id:your_key_secret"
```

### 5. Run the app

```bash
streamlit run app.py
```

This opens a browser tab at `localhost:8501`.

## Usage

1. Enter a description of the video you want
2. Choose an aspect ratio
3. Click **Generate video**
4. Wait 1–3 minutes while it renders
5. Preview and download the result

## Cost

This app uses your own fal.ai API key and balance. Veo 3 Fast is priced per second of generated video (roughly $0.10–0.15/sec at time of writing) — check [fal.ai's pricing](https://fal.ai/pricing) for current rates.

## Deployment

This app is set up to run on [Streamlit Community Cloud](https://share.streamlit.io). Add your `FAL_KEY` under **App settings → Secrets** in this format:

```
FAL_KEY = "your_key_id:your_key_secret"
```

## Notes

⚠️ This is an early-stage prototype, not a production app. There's currently no rate limiting or access control, so anyone with a link to a deployed instance can generate videos against the connected API key.

## License

MIT
=======
# Video-generator
A minimal web app for generating short AI videos from text prompts, built with Streamlit and fal.ai's Veo 3 API.
