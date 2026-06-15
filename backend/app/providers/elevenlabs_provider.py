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


class ElevenLabsProvider(TTSProvider):
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.elevenlabs.io",
        model_id: str = "eleven_multilingual_v2",
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id

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
        body: dict = {"text": text, "model_id": self._model_id}
        if voice_settings:
            body["voice_settings"] = voice_settings

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
