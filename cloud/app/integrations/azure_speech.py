import tempfile
from pathlib import Path
from typing import Optional


def transcribe_audio_with_azure(
    audio_bytes: bytes,
    azure_openai_client,
    azure_openai_stt_deployment: str,
    file_name: str = "voice.ogg",
) -> Optional[str]:
    """Transcribe audio bytes using Azure OpenAI transcription deployment."""
    if azure_openai_client is None or not azure_openai_stt_deployment:
        print("[Azure STT] ⚠️ Missing Azure OpenAI client or STT deployment")
        return None

    suffix = Path(file_name).suffix or ".ogg"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            temp_path = tmp.name

        with open(temp_path, "rb") as f:
            result = azure_openai_client.audio.transcriptions.create(
                model=azure_openai_stt_deployment,
                file=f,
            )

        transcript = (getattr(result, "text", "") or "").strip()
        if transcript:
            print(f"[Azure STT] ✅ Transcript: {transcript[:80]}")
            return transcript

    except Exception as e:
        print(f"[Azure STT] ❌ Transcription failed: {e}")

    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink()
            except Exception:
                pass

    return None


def synthesize_voice_with_azure(
    text: str,
    azure_speech_available: bool,
    azure_speech_key: str,
    azure_speech_region: str,
    azure_speech_voice: str,
) -> Optional[bytes]:
    """Synthesize text to WAV using Azure Speech."""
    if not text:
        return None

    if not azure_speech_available or not azure_speech_key or not azure_speech_region:
        print("[Azure TTS] ⚠️ Speech SDK/key/region not configured")
        return None

    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        print("[Azure TTS] ⚠️ Azure Speech SDK not installed")
        return None

    temp_path = None

    try:
        speech_config = speechsdk.SpeechConfig(
            subscription=azure_speech_key,
            region=azure_speech_region,
        )
        speech_config.speech_synthesis_voice_name = azure_speech_voice
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            temp_path = tmp.name

        audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_path)
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted and Path(temp_path).exists():
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            print("[Azure TTS] ✅ Voice generated")
            return audio_bytes

        print(f"[Azure TTS] ❌ Synthesis failed: {result.reason}")

    except Exception as e:
        print(f"[Azure TTS] ❌ Error: {e}")

    finally:
        if temp_path and Path(temp_path).exists():
            try:
                Path(temp_path).unlink()
            except Exception:
                pass

    return None