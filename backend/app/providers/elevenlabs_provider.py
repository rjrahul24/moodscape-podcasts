"""ElevenLabs implementation of :class:`TTSProvider`.

Uses the REST API directly via httpx (no SDK dependency) so the surface area
we depend on is explicit:

* ``GET  /v1/voices``                  -> list available voices
* ``POST /v1/text-to-speech/{voice}``  -> synthesize a chunk of text
"""

from __future__ import annotations

import httpx
from pydub import AudioSegment

from app.core.errors import ProviderError
from app.core.models import Voice
from app.core.stitcher import bytes_to_segment

from .base import TTSProvider

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# ElevenLabs has two generations with *different* control surfaces, so the
# provider tailors itself to whichever the caller selected (per speaker / per
# sleep story) AND to the content type (expressive podcast vs calm sleep):
#
#   * v2 (eleven_multilingual_v2): numeric stability / similarity_boost / style
#     knobs + a native speed (0.7–1.2). Best text normalization. A recognized
#     tone tag maps to a numeric profile; the tag text itself is stripped.
#   * v3 (eleven_v3): discrete stability (Creative 0.0 / Natural 0.5 / Robust
#     1.0) + *inline performed audio tags* ([excited], [whispers], …). Here the
#     tag is injected into the text so the model actually performs it.
V3_MODEL = "eleven_v3"

# v2 — tone tag -> numeric voice_settings (podcast, expressive).
EMOTION_PROFILES: dict[str, dict[str, float]] = {
    "excited": {"stability": 0.30, "similarity_boost": 0.85, "style": 0.80},
    "calm": {"stability": 0.85, "similarity_boost": 0.75, "style": 0.10},
    "sad": {"stability": 0.70, "similarity_boost": 0.80, "style": 0.40},
    "whispering": {"stability": 0.90, "similarity_boost": 0.60, "style": 0.05},
    "neutral": {"stability": 0.55, "similarity_boost": 0.80, "style": 0.25},
}

# v2 — per-content-type base profile used when no tone tag is present. Podcasts
# lean expressive (lower stability, some style); sleep leans calm and steady
# (high stability, no style) so the *voice itself* narrates gently — the sleep
# mastering chain then sits on top.
V2_CONTENT_BASE: dict[str, dict[str, float]] = {
    "podcast": {"stability": 0.45, "similarity_boost": 0.80, "style": 0.45},
    "sleep": {"stability": 0.88, "similarity_boost": 0.80, "style": 0.0},
}

# v3 — tone tag -> inline performed audio tag prepended to the chunk text.
V3_AUDIO_TAGS: dict[str, str] = {
    "excited": "[excited]",
    "whispering": "[whispers]",
    "calm": "[calm]",
    "sad": "[sad]",
    "neutral": "",
}

# v3 — discrete stability per content type (Natural for podcasts, Robust for the
# steady consistency a sleep story wants). An [excited] turn drops to Creative.
V3_STABILITY: dict[str, float] = {"podcast": 0.5, "sleep": 1.0}

_SPEED_MIN, _SPEED_MAX = 0.7, 1.2


def _clamp_speed(speed: float) -> float:
    return max(_SPEED_MIN, min(_SPEED_MAX, float(speed)))


class ElevenLabsProvider(TTSProvider):
    name = "elevenlabs"
    has_native_speed = True

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.elevenlabs.io",
        model_id: str = "eleven_multilingual_v2",
        podcast_model: str | None = None,
        sleep_model: str | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        # Per-content-type default model used when the request doesn't pin one.
        self._podcast_model = podcast_model or model_id
        self._sleep_model = sleep_model or model_id

    # ── helpers ───────────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise ProviderError(
                self.name,
                "ELEVENLABS_API_KEY is not set. Add it to backend/.env.",
                status_code=401,
            )
        return {"xi-api-key": self._api_key}

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        detail = ""
        try:
            body = response.json()
            detail = body.get("detail") or body
        except Exception:  # noqa: BLE001 - body may not be JSON
            detail = response.text[:300]
        raise ProviderError(
            "elevenlabs",
            f"{action} failed ({response.status_code}): {detail}",
            status_code=response.status_code,
        )

    def _prepare(
        self, text: str, voice_settings: dict | None
    ) -> tuple[str, str, dict | None]:
        """Resolve (text, model_id, voice_settings body) for one synthesis call.

        Reads the orchestrator's per-chunk hints — ``content_type``, ``model_id``,
        ``emotion``, ``speed`` — and tailors them to the selected ElevenLabs
        generation. For v3 the tone tag is performed *inline* (prepended to the
        text); for v2 it maps to a numeric profile. Any explicit EL keys the
        caller passed (``stability`` etc.) win over the computed profile.
        """
        vs = dict(voice_settings or {})
        content_type = vs.pop("content_type", "podcast")
        model_id = vs.pop("model_id", None) or (
            self._sleep_model if content_type == "sleep" else self._podcast_model
        )
        emotion = vs.pop("emotion", None)
        speed = vs.pop("speed", None)
        # Whatever remains is an explicit EL override (stability/style/…).

        if model_id == V3_MODEL:
            text, body = self._prepare_v3(text, content_type, emotion, speed)
        else:
            body = self._prepare_v2(content_type, emotion, speed)
        body.update(vs)
        return text, model_id, (body or None)

    @staticmethod
    def _prepare_v2(
        content_type: str, emotion: str | None, speed: float | None
    ) -> dict:
        if emotion and emotion in EMOTION_PROFILES:
            profile = dict(EMOTION_PROFILES[emotion])
        else:
            profile = dict(V2_CONTENT_BASE.get(content_type, V2_CONTENT_BASE["podcast"]))
        if speed is not None:
            profile["speed"] = _clamp_speed(speed)
        return profile

    @staticmethod
    def _prepare_v3(
        text: str, content_type: str, emotion: str | None, speed: float | None
    ) -> tuple[str, dict]:
        tag = V3_AUDIO_TAGS.get(emotion or "", "")
        if tag:
            text = f"{tag} {text}"
        stability = V3_STABILITY.get(content_type, 0.5)
        if emotion == "excited":
            stability = 0.0  # Creative for high energy
        body: dict = {"stability": stability, "similarity_boost": 0.85}
        if content_type == "podcast":
            body["style"] = 0.5
        if speed is not None:
            body["speed"] = _clamp_speed(speed)
        return text, body

    # ── interface ─────────────────────────────────────────────────────────────
    def list_voices(self) -> list[Voice]:
        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                response = client.get(
                    f"{self._base_url}/v1/voices", headers=self._headers()
                )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"could not reach ElevenLabs: {exc}") from exc

        self._raise_for_status(response, "Listing voices")
        payload = response.json()
        return [
            Voice(
                id=item["voice_id"],
                name=item.get("name", item["voice_id"]),
                provider=self.name,
                category=item.get("category"),
            )
            for item in payload.get("voices", [])
        ]

    def synthesize_bytes(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str,
        voice_settings: dict | None = None,
    ) -> bytes:
        """Request encoded audio bytes from the ElevenLabs API."""
        text, model_id, resolved = self._prepare(text, voice_settings)
        body: dict = {"text": text, "model_id": model_id}
        if resolved:
            body["voice_settings"] = resolved

        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                response = client.post(
                    f"{self._base_url}/v1/text-to-speech/{voice_id}",
                    headers={**self._headers(), "accept": "audio/*"},
                    params={"output_format": output_format},
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"synthesis request failed: {exc}") from exc

        self._raise_for_status(response, f"Synthesis (voice {voice_id})")
        return response.content

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        output_format: str,
        voice_settings: dict | None = None,
    ) -> AudioSegment:
        data = self.synthesize_bytes(
            text, voice_id, output_format=output_format, voice_settings=voice_settings
        )
        return bytes_to_segment(data, output_format)
