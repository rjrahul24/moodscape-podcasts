# Assets — F5 reference voices

F5 TTS clones a voice from a short reference clip. To add a voice, drop two
files here with the **same base name**:

```
assets/speakers/
  reference_audio/<name>.wav    # 10–12 s of clean speech, mono (any sample rate)
  reference_text/<name>.txt     # the EXACT words spoken in that clip (verbatim)
```

Example:

```
assets/speakers/reference_audio/brittney.wav
assets/speakers/reference_text/brittney.txt   ->  "Allow your body to sink into rest..."
```

Rules:
- Both files are required. A `.wav` without a matching `.txt` is skipped (it
  won't appear in the dropdown).
- The transcript must match the audio word-for-word — mismatches cause artifacts.
- Keep the clip short (≤12 s); F5 clips longer references internally.
- The voice's display name is the file name, title-cased (`calm_brittney` →
  "Calm Brittney").

Restart the backend after adding files; the voice then appears under the **F5**
provider in each speaker's voice dropdown.
