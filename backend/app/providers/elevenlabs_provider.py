"""ElevenLabs implementation of :class:`TTSProvider`.

Uses the REST API directly via httpx (no SDK dependency) so the surface area
we depend on is explicit:

* ``GET  /v1/voices``                  -> list available voices
* ``POST /v1/text-to-speech/{voice}``  -> synthesize a chunk of text
"""

from __future__ import annotations

import re

import httpx
from pydub import AudioSegment

from app.core.errors import ProviderError
from app.core.models import Voice
from app.core.stitcher import bytes_to_segment

from .base import TTSProvider

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# Any ``[bracketed]`` token. v3 *performs* these (kept in the text); v2 cannot, so
# they are stripped before synthesis so the model never speaks the literal tag.
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")

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
    # Mindfulness-leaning tones: gently warm with real prosodic life. ``soothing``
    # is the default sleep tone — moderate ``style`` gives v2 emotional warmth
    # (it can't perform inline tags, so the feeling has to come from the voice
    # setting) while a mid-high stability keeps it steady, not a flat drone. (warm
    # / reflective are shared with podcast v2, so they keep their original values.)
    "soothing": {"stability": 0.68, "similarity_boost": 0.82, "style": 0.22},
    "reflective": {"stability": 0.80, "similarity_boost": 0.78, "style": 0.20},
    "warm": {"stability": 0.75, "similarity_boost": 0.82, "style": 0.30},
    "dreamy": {"stability": 0.85, "similarity_boost": 0.78, "style": 0.10},
    "tender": {"stability": 0.72, "similarity_boost": 0.82, "style": 0.25},
}

# v2 — per-content-type base profile used when no tone tag is present. Podcasts
# lean expressive but keep ``style`` at 0.0 (research: unforced, organic dialogue
# — style exaggeration introduces dramatic flair that reads as artificial). Sleep
# sits at the research sweet spot (stability ~0.70, no style) — warm and steady
# without a robotic drone; the sleep mastering chain then sits on top.
V2_CONTENT_BASE: dict[str, dict[str, float]] = {
    "podcast": {"stability": 0.50, "similarity_boost": 0.80, "style": 0.0},
    "sleep": {"stability": 0.70, "similarity_boost": 0.80, "style": 0.0},
}

# v3 — tone tag -> inline performed audio tag prepended to the chunk text.
V3_AUDIO_TAGS: dict[str, str] = {
    "excited": "[excited]",
    "whispering": "[whispers]",
    "calm": "[calm]",
    "sad": "[sad]",
    "neutral": "",
    "soothing": "[calm]",
    "reflective": "[thoughtful]",
    "warm": "[warmly]",
    "dreamy": "[calm]",
    "tender": "[warmly]",
}

# v3 — discrete stability per content type (Natural for podcasts; sleep is set
# from config, default Natural 0.5 so the calming inline tags stay responsive).
# An [excited] turn drops to Creative.
V3_STABILITY: dict[str, float] = {"podcast": 0.5, "sleep": 0.5}

# v3 ignores SSML break tags, but native multilingual v2 honours them — used to
# turn an author's [pause:N] or bare [pause] marker into a real, model-aware breath.
V2_MODEL = "eleven_multilingual_v2"
_PAUSE_MARKER_RE = re.compile(r"\[\s*pause\s*(?::\s*(\d+)\s*(?:ms)?\s*)?\s*\]", re.IGNORECASE)
_BREAK_MAX_S = 3.0  # ElevenLabs caps a single <break> at 3 seconds
_BREAK_DEFAULT_S = 1.0  # bare [pause] (no duration) defaults to 1 second

_SPEED_MIN, _SPEED_MAX = 0.7, 1.2


def _clamp_speed(speed: float) -> float:
    return max(_SPEED_MIN, min(_SPEED_MAX, float(speed)))


def _pause_markers_to_breaks(text: str) -> str:
    """Rewrite ``[pause:800]`` / ``[pause:800ms]`` / ``[pause]`` → ``<break time="…s"/>``.

    v2 renders the native break with model-aware prosody around it — smoother than
    a spliced silence. Durations are clamped to ElevenLabs' 3 s per-break ceiling.
    A bare ``[pause]`` uses ``_BREAK_DEFAULT_S``. The angle-bracket tag survives
    ``_strip_bracket_tags`` (which only removes ``[...]``), so it reaches the API
    intact.
    """

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        seconds = min(int(raw) / 1000.0, _BREAK_MAX_S) if raw is not None else _BREAK_DEFAULT_S
        return f'<break time="{seconds:.2f}s"/>'

    return _PAUSE_MARKER_RE.sub(repl, text)


def _strip_bracket_tags(text: str) -> str:
    """Remove ``[...]`` tags and collapse the whitespace they leave behind.

    Used on the v2 path, which has no inline-tag vocabulary — left in, a tag like
    ``[exhales softly]`` is read aloud or garbles prosody.
    """
    return re.sub(r"\s{2,}", " ", _BRACKET_TAG_RE.sub("", text)).strip()


class ElevenLabsProvider(TTSProvider):
    name = "elevenlabs"
    has_native_speed = True
    accepts_inline_sfx = True  # v3 performs [warmly], [exhales softly], [deep_breath], …
    accepts_continuity = True  # accepts previous_text / next_text for cross-chunk prosody

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.elevenlabs.io",
        model_id: str = "eleven_multilingual_v2",
        podcast_model: str | None = None,
        sleep_model: str | None = None,
        use_speaker_boost: bool = True,
        text_normalization: str = "auto",
        sleep_v3_stability: float = 0.5,
        sleep_v3_pacing_tag: str = "",
        v2_native_breaks: bool = True,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        # Per-content-type default model used when the request doesn't pin one.
        self._podcast_model = podcast_model or model_id
        self._sleep_model = sleep_model or model_id
        self._use_speaker_boost = use_speaker_boost
        self._text_normalization = text_normalization
        self._sleep_v3_stability = sleep_v3_stability
        self._sleep_v3_pacing_tag = sleep_v3_pacing_tag.strip()
        self._v2_native_breaks = v2_native_breaks

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
    ) -> tuple[str, str, dict | None, dict]:
        """Resolve (text, model_id, voice_settings body, top-level extras).

        Reads the orchestrator's per-chunk hints — ``content_type``, ``model_id``,
        ``emotion``, ``speed`` — and tailors them to the selected ElevenLabs
        generation. For v3 the tone tag is performed *inline* (prepended to the
        text) and any other ``[...]`` tags are kept for the model to perform; for
        v2 the tone tag maps to a numeric profile and *all* bracket tags are
        stripped from the text. Cross-chunk continuity (``previous_text`` /
        ``next_text``) and ``seed`` are returned as top-level request-body extras.
        Any explicit EL keys the caller passed (``stability`` etc.) win over the
        computed profile.
        """
        vs = dict(voice_settings or {})
        content_type = vs.pop("content_type", "podcast")
        model_id = vs.pop("model_id", None) or (
            self._sleep_model if content_type == "sleep" else self._podcast_model
        )
        emotion = vs.pop("emotion", None)
        speed = vs.pop("speed", None)
        # Continuity / determinism ride alongside voice_settings but are top-level
        # request fields, not voice-settings keys — pull them out here.
        extras: dict = {}
        prev_text = vs.pop("previous_text", None)
        next_text = vs.pop("next_text", None)
        seed = vs.pop("seed", None)
        if seed is not None:
            extras["seed"] = seed
        # Whatever remains is an explicit EL override (stability/style/…).

        if model_id == V3_MODEL:
            text, body = self._prepare_v3(text, content_type, emotion, speed)
        else:
            text, body = self._prepare_v2(text, content_type, emotion, speed)
            if prev_text:
                extras["previous_text"] = prev_text
            if next_text:
                extras["next_text"] = next_text
        body["use_speaker_boost"] = self._use_speaker_boost
        body.update(vs)
        return text, model_id, (body or None), extras

    def _prepare_v2(
        self, text: str, content_type: str, emotion: str | None, speed: float | None
    ) -> tuple[str, dict]:
        if emotion and emotion in EMOTION_PROFILES:
            profile = dict(EMOTION_PROFILES[emotion])
        else:
            profile = dict(V2_CONTENT_BASE.get(content_type, V2_CONTENT_BASE["podcast"]))
        if speed is not None:
            profile["speed"] = _clamp_speed(speed)
        # Render author breaths as native <break> tags (kept after the [...] strip),
        # else they'd be dropped along with the other bracket tags.
        if self._v2_native_breaks:
            text = _pause_markers_to_breaks(text)
        return _strip_bracket_tags(text), profile

    def _prepare_v3(
        self, text: str, content_type: str, emotion: str | None, speed: float | None
    ) -> tuple[str, dict]:
        # Build the inline tag prefix: emotion tag first, then (for sleep) the
        # reasserted pacing tag — e.g. "[calm] [slowly] …". The pacing tag holds
        # v3's slow, calm register on every chunk so a long story doesn't drift
        # toward an audiobook read.
        prefix = ""
        tag = V3_AUDIO_TAGS.get(emotion or "", "")
        if tag:
            prefix += f"{tag} "
        if content_type == "sleep" and self._sleep_v3_pacing_tag:
            prefix += f"{self._sleep_v3_pacing_tag} "
        if prefix:
            text = f"{prefix}{text}"
        stability = self._sleep_v3_stability if content_type == "sleep" else V3_STABILITY.get(
            content_type, 0.5
        )
        if emotion == "excited":
            stability = 0.0  # Creative for high energy
        body: dict = {"stability": stability, "similarity_boost": 0.80}
        if content_type == "podcast":
            # Unforced, organic dialogue — research recommends style 0.0 over the
            # model's tendency to over-dramatize.
            body["style"] = 0.0
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
        text, model_id, resolved, extras = self._prepare(text, voice_settings)
        words_only = _BRACKET_TAG_RE.sub("", text).strip()
        if not words_only:
            raise ProviderError(
                self.name,
                "Synthesis received text with no actual words after removing "
                "bracket tags (got only tags like [laughs]/[sighs]). "
                "Ensure every turn has spoken words, not just delivery cues.",
            )
        body: dict = {"text": text, "model_id": model_id}
        if resolved:
            body["voice_settings"] = resolved
        if self._text_normalization:
            body["apply_text_normalization"] = self._text_normalization
        # previous_text / next_text (cross-chunk prosody) and seed (determinism).
        body.update(extras)

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
