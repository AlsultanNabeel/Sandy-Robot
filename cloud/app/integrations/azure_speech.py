import tempfile
from pathlib import Path
from typing import Optional


def transcribe_audio_with_azure(
    audio_bytes: bytes,
    azure_speech_available: bool,
    azure_speech_key: str,
    azure_speech_region: str,
    file_name: str = "voice.ogg",
    recognition_language: str = "ar-EG",
) -> Optional[str]:
    """Transcribe audio bytes using Azure Speech SDK."""
    if not audio_bytes:
        return None

    if not azure_speech_available or not azure_speech_key or not azure_speech_region:
        print("[Azure STT] ⚠️ Speech SDK/key/region not configured")
        return None

    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        print("[Azure STT] ⚠️ Azure Speech SDK not installed")
        return None

    import subprocess
    import tempfile
    from pathlib import Path

    suffix = Path(file_name).suffix or ".ogg"
    temp_input = None
    temp_wav = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            temp_input = tmp.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_wav:
            temp_wav = tmp_wav.name

        convert_cmd = [
            "ffmpeg",
            "-y",
            "-i", temp_input,
            "-ac", "1",
            "-ar", "16000",
            "-f", "wav",
            temp_wav,
        ]
        subprocess.run(convert_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        speech_config = speechsdk.SpeechConfig(
            subscription=azure_speech_key,
            region=azure_speech_region,
        )
        speech_config.speech_recognition_language = recognition_language

        audio_config = speechsdk.audio.AudioConfig(filename=temp_wav)
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config,
        )

        result = recognizer.recognize_once_async().get()

        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            transcript = (result.text or "").strip()
            if transcript:
                print(f"[Azure STT] ✅ Transcript: {transcript[:80]}")
                return transcript

        if result.reason == speechsdk.ResultReason.NoMatch:
            print("[Azure STT] ⚠️ No speech could be recognized")
            return None

        if result.reason == speechsdk.ResultReason.Canceled:
            details = speechsdk.CancellationDetails(result)
            print(
                f"[Azure STT] ❌ Canceled: reason={details.reason}, "
                f"error_details={details.error_details}"
            )
            return None

        print(f"[Azure STT] ❌ Unexpected recognition result: {result.reason}")

    except subprocess.CalledProcessError:
        print("[Azure STT] ❌ ffmpeg failed to convert audio to wav")
    except Exception as e:
        print(f"[Azure STT] ❌ Transcription failed: {e}")

    finally:
        for p in [temp_input, temp_wav]:
            if p and Path(p).exists():
                try:
                    Path(p).unlink()
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