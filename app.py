# app_combined.py
import os
import wave
import base64
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO
import azure.cognitiveservices.speech as speechsdk
from werkzeug.utils import secure_filename
import config

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

recognizer_instance = None
default_languages = ["en-US", "si-LK", "ja-JP", "fr-FR", "wuu-CN", "es-ES", "de-DE", "ru-RU", "hi-IN"]

def get_speech_config():
    return speechsdk.SpeechConfig(subscription=config.AZURE_SPEECH_KEY, region=config.AZURE_REGION)

# ---------------------- LIVE MICROPHONE TRANSLATION ---------------------- #

def recognize_speech(target_language, source_language, event_name):
    global recognizer_instance

    translation_config = speechsdk.translation.SpeechTranslationConfig(
        subscription=config.AZURE_SPEECH_KEY,
        endpoint=f"wss://{config.AZURE_REGION}.stt.speech.microsoft.com/speech/universal/v2"
    )
    translation_config.add_target_language(target_language)
    translation_config.speech_recognition_language = source_language

    recognizer_instance = speechsdk.translation.TranslationRecognizer(
        translation_config=translation_config,
        audio_config=speechsdk.audio.AudioConfig(use_default_microphone=True)
    )

    def recognized_callback(evt):
        original_text = evt.result.text
        translated_text = evt.result.translations.get(target_language, "")

        # TTS step
        speech_config = get_speech_config()
        speech_config.speech_synthesis_language = target_language
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
        tts_result = synthesizer.speak_text_async(translated_text).get()

        if tts_result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            audio_data = tts_result.audio_data
            audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        else:
            audio_base64 = None  # fallback if it fails

        payload = {
            "original": original_text,
            "translated": translated_text,
            "audio": audio_base64,
            "target": "agent" if event_name == "customer_translation_update" else "customer"
        }

        if event_name == "customer_translation_update":
            socketio.emit("show_customer_original", {"original": original_text})
            socketio.emit("send_to_agent_translated", payload)
        elif event_name == "agent_translation_update":
            socketio.emit("show_agent_original", {"original": original_text})
            socketio.emit("send_to_customer_translated", payload)

    recognizer_instance.recognized.connect(recognized_callback)
    recognizer_instance.start_continuous_recognition()

@socketio.on("start_customer_speech")
def start_customer_speech(data):
    recognize_speech(data.get("target_language"), data.get("source_language"), "customer_translation_update")
    socketio.emit("listening", {"side": "customer"})

@socketio.on("start_agent_speech")
def start_agent_speech(data):
    recognize_speech(data.get("target_language"), data.get("source_language"), "agent_translation_update")
    socketio.emit("listening", {"side": "agent"})

@socketio.on("stop_speech")
def stop_speech():
    global recognizer_instance
    if recognizer_instance:
        recognizer_instance.stop_continuous_recognition_async()
        recognizer_instance = None
    socketio.emit("stopped_listening")

# ---------------------- WAV FILE UPLOAD + TTS ---------------------- #

def validate_wav_file(file_path):
    try:
        with wave.open(file_path) as wav_file:
            if wav_file.getnchannels() != 1:
                return "Audio must be mono (1 channel)"
            if wav_file.getsampwidth() != 2:
                return "Audio must be 16-bit PCM"
            if wav_file.getframerate() not in [8000, 16000, 44100]:
                return "Sample rate must be 8kHz, 16kHz, or 44.1kHz"
        return None
    except Exception as e:
        return f"Invalid WAV file: {str(e)}"

def text_to_speech(text, language, output_path):
    try:
        speech_config = get_speech_config()
        speech_config.speech_synthesis_language = language
        voice_map = {
            "si-LK": "si-LK-SameeraNeural",  
            "en-US": "en-US-GuyNeural",
            "fr-FR": "fr-FR-HenriNeural",
            "ja-JP": "ja-JP-NanamiNeural",
            "wuu-CN": "wuu-CN-XiaotongNeural",
            "es-ES": "es-ES-ElviraNeural", 
            "de-DE": "de-DE-KatjaNeural", 
            "ru-RU": "ru-RU-SvetlanaNeural", 
            "hi-IN": "hi-IN-AaravNeural"
        }
        speech_config.speech_synthesis_voice_name = voice_map.get(language, "en-US-GuyNeural")

        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()

        return output_path if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted else None
    except:
        return None

def process_audio_translation(file_path, source_lang, target_lang, role):
    translation_config = speechsdk.translation.SpeechTranslationConfig(
        subscription=config.AZURE_SPEECH_KEY,
        region=config.AZURE_REGION,
        speech_recognition_language=source_lang
    )
    translation_config.add_target_language(target_lang)
    audio_config = speechsdk.audio.AudioConfig(filename=file_path)
    recognizer = speechsdk.translation.TranslationRecognizer(
        translation_config=translation_config,
        audio_config=audio_config
    )
    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.TranslatedSpeech:
        original = result.text
        translated = result.translations.get(target_lang[:2], "")
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f"translated_{os.path.basename(file_path)}")
        speech_file = text_to_speech(translated, target_lang, output_path)

        if role == "customer":
            socketio.emit("show_customer_original", {"original": original})
            socketio.emit("send_to_agent_translated", {"original": original, "translated": translated, "audio_url": f"/download/{os.path.basename(speech_file)}"})
        else:
            socketio.emit("show_agent_original", {"original": original})
            socketio.emit("send_to_customer_translated", {"original": original, "translated": translated, "audio_url": f"/download/{os.path.basename(speech_file)}"})

        return {"status": "success", "original": original, "translated": translated, "audio_url": f"/download/{os.path.basename(speech_file)}"}
    return {"status": "error", "message": "Translation failed"}

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    error = validate_wav_file(file_path)
    if error:
        os.remove(file_path)
        return jsonify({"status": "error", "message": error}), 400

    result = process_audio_translation(file_path, request.form.get("source_lang"), request.form.get("target_lang"), request.form.get("role"))
    os.remove(file_path)
    return jsonify(result), 200 if result["status"] == "success" else 500

@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

# ---------------------- MISC SOCKET EVENTS + ROUTES ---------------------- #

@socketio.on("send_to_agent")
def send_to_agent(data):
    socketio.emit("receive_customer_message", data)

@socketio.on("send_to_customer")
def send_to_customer(data):
    socketio.emit("receive_agent_response", data)

@socketio.on("update_agent_language")
def handle_update_agent_language(lang):
    socketio.emit("update_agent_language", lang)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/customer")
def customer():
    return render_template("customer.html")

@app.route("/agent")
def agent():
    return render_template("agent.html")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
