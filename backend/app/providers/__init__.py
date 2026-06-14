"""TTS provider abstraction and registry.

Adding a new provider (e.g. VibeVoice) is intentionally a closed change to the
rest of the system:

1. Implement :class:`~app.providers.base.TTSProvider`.
2. Register an instance in :func:`~app.providers.bootstrap.bootstrap_providers`.
3. (Optionally) add its voice ids to ``VOICE_CATALOG``.

The script parser, engine, stitcher, API and frontend stay untouched.
"""
