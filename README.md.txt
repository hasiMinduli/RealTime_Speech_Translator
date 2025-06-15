# Real-Time Call Center Translator 🎙️🌐

A Flask-based interface for real-time speech translation using mic and WAV input.

## Features
- 🎤 Mic-based real-time STT + translation
- 📤 WAV file upload support
- 🗣️ TTS in multiple languages
- 💬 Agent + Customer interfaces
- 🔁 Bidirectional translation flow

## Tech Stack
- Flask
- Socket.IO
- Azure Speech Services
- HTML + CSS + JS (vanilla)

## How to setup

1. Clone or download this repo.
2. Create a file named `config.py` in the root folder.
3. Inside `config.py`, add your Azure keys like this:

```python

AZURE_SPEECH_KEY = "your_azure_speech_key"
AZURE_REGION = "your_azure_region"

4.Install the needed python packages

```bash
pip install -r requirements.txt

5.Run the app

## How to Run

```bash
python app.py

⚠️ Remember: Never share your config.py with your real keys publicly!