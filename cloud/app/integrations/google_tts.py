from typing import Dict, Optional


def synthesize_voice_with_google(
    text: str,
    mood: str = "neutral",
    style: str = "normal",
    google_tts_voice: str = "",
    google_tts_language_code: str = "en-US",
    mood_tts_voices: Optional[Dict[str, str]] = None,
) -> Optional[bytes]:
    """Synthesize speech with Google TTS and return WAV bytes."""
    if not text:
        return None

    try:
        from google.cloud import texttospeech
    except ImportError:
        print("[Google TTS] ⚠️ google-cloud-texttospeech not installed")
        return None

    mood_tts_voices = mood_tts_voices or {}

    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)

        selected_voice = mood_tts_voices.get(mood, google_tts_voice)

        if style == "romantic":
            selected_voice = mood_tts_voices.get("romantic", selected_voice)
        elif style == "caring":
            if mood in ["sad", "angry", "neutral"]:
                selected_voice = mood_tts_voices.get("sad", selected_voice)
        elif style == "serious":
            selected_voice = mood_tts_voices.get("serious", selected_voice)
        elif style == "excited":
            selected_voice = mood_tts_voices.get("excited", selected_voice)
        elif style == "shy":
            selected_voice = mood_tts_voices.get("shy", selected_voice)
        elif style == "playful":
            selected_voice = mood_tts_voices.get("happy", selected_voice)

        print(f"[Google TTS] Using mood='{mood}' voice='{selected_voice}'")

        voice = texttospeech.VoiceSelectionParams(
            language_code=google_tts_language_code,
            name=selected_voice,
            ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
        )

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        return response.audio_content

    except Exception as e:
        print(f"[Google TTS] ❌ Error: {e}")
        return None