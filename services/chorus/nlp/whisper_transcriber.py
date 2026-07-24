"""Whisper ASR transcriber for WhatsApp voice notes.

Uses OpenAI Whisper (multilingual) to transcribe Hindi, Assamese,
Bengali, and English voice notes received via the Twilio webhook.

Falls back to empty transcription when the whisper package or
model checkpoint is unavailable (hackathon demo safety).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Try to import whisper — fall back gracefully
try:
    import whisper as _whisper  # type: ignore[import-untyped]
    _WHISPER_AVAILABLE = True
except ImportError:
    _whisper = None
    _WHISPER_AVAILABLE = False
    logger.warning("whisper_not_available", hint="pip install openai-whisper")

# Try to import httpx for media download
try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False


@dataclass
class TranscriptionResult:
    """Output of a speech-to-text transcription."""
    text: str = ""
    language_detected: str = "unknown"
    confidence: float = 0.0
    duration_seconds: float = 0.0
    error: Optional[str] = None


class WhisperTranscriber:
    """Transcribes WhatsApp voice notes to text.

    Uses OpenAI Whisper ``base`` model for hackathon (fast).
    Production would use ``medium`` or ``large-v3``.
    The multilingual model handles Hindi, Assamese, Bengali natively.
    """

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self._model = None
        if _WHISPER_AVAILABLE:
            try:
                self._model = _whisper.load_model(model_size)
                logger.info("whisper_loaded", model=model_size)
            except Exception as exc:
                logger.error("whisper_load_failed", error=str(exc))

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def transcribe(
        self,
        audio_bytes: bytes,
        language_hint: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe raw audio bytes.

        Args:
            audio_bytes: Raw audio file content (WAV, OGG, MP3).
            language_hint: Optional ISO 639-1 code (e.g. ``"hi"``).

        Returns:
            TranscriptionResult with text and detected language.
        """
        if not self.is_available:
            return TranscriptionResult(error="Whisper model not loaded")

        # Write bytes to temp file (whisper requires file path)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            options = {}
            if language_hint:
                options["language"] = language_hint

            result = self._model.transcribe(tmp_path, **options)
            segments = result.get("segments", [])
            avg_confidence = 0.0
            total_duration = 0.0
            if segments:
                avg_confidence = sum(
                    s.get("avg_logprob", -1.0) for s in segments
                ) / len(segments)
                # Convert log-prob to 0-1 confidence (rough heuristic)
                avg_confidence = max(0.0, min(1.0, 1.0 + avg_confidence))
                total_duration = segments[-1].get("end", 0.0)

            return TranscriptionResult(
                text=result.get("text", "").strip(),
                language_detected=result.get("language", language_hint or "unknown"),
                confidence=round(avg_confidence, 3),
                duration_seconds=round(total_duration, 1),
            )
        except Exception as exc:
            logger.error("transcription_failed", error=str(exc))
            return TranscriptionResult(error=str(exc))
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def transcribe_url(
        self,
        media_url: str,
        auth: Optional[tuple] = None,
    ) -> TranscriptionResult:
        """Download audio from a URL (e.g. Twilio media) and transcribe.

        Args:
            media_url: URL to download audio from.
            auth: Optional ``(username, password)`` tuple for HTTP Basic auth
                  (required for Twilio media URLs).

        Returns:
            TranscriptionResult.
        """
        if not _HTTPX_AVAILABLE:
            return TranscriptionResult(error="httpx not available for URL download")

        try:
            kwargs = {"timeout": 30.0}
            if auth:
                kwargs["auth"] = auth  # type: ignore[assignment]
            resp = httpx.get(media_url, **kwargs)
            resp.raise_for_status()
            return self.transcribe(resp.content)
        except Exception as exc:
            logger.error("media_download_failed", url=media_url, error=str(exc))
            return TranscriptionResult(error=f"Download failed: {exc}")
