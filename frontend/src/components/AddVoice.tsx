import { useState } from "react";
import { uploadReferenceVoice } from "../api/client";
import type { ReferenceVoiceCreated } from "../types";
import { Icon } from "./Icon";

interface Props {
  // Called after a successful upload so the parent can refresh the voice list.
  onAdded: (voice: ReferenceVoiceCreated) => void;
}

// Upload a short clip to clone. The clip is cleaned server-side (mono, resample,
// silence-trim, optional denoise) and added to F5's voices.
export function AddVoice({ onAdded }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [transcript, setTranscript] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<ReferenceVoiceCreated | null>(null);

  const ready = name.trim().length > 0 && file !== null && !busy;

  async function submit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await uploadReferenceVoice({ name, audio: file, transcript });
      setDone(result);
      onAdded(result);
      setName("");
      setTranscript("");
      setFile(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>
          <Icon name="mic" /> Clone a voice
        </h2>
        <button
          type="button"
          className="link-button"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Hide" : "Add a voice"}
        </button>
      </div>

      {open && (
        <div className="sleep-grid">
          <label className="field">
            <span className="field-label">Voice name</span>
            <input
              type="text"
              value={name}
              placeholder="e.g. Calm River"
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          <label className="field">
            <span className="field-label">Reference clip</span>
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <span className="hint">
              A short, clean clip (≈10–30s). It’s denoised and trimmed for you.
            </span>
          </label>

          <label className="field field-wide">
            <span className="field-label">Transcript</span>
            <input
              type="text"
              value={transcript}
              placeholder="The exact words spoken in the clip (recommended)."
              onChange={(e) => setTranscript(e.target.value)}
            />
            <span className="hint">
              Leave blank to auto-transcribe (needs the <code>qc</code> extra).
              Cloning is most accurate with an exact transcript.
            </span>
          </label>

          <div className="field field-wide">
            <button className="generate" onClick={submit} disabled={!ready}>
              {busy ? (
                <Icon name="loader" size={18} className="spin" />
              ) : (
                <Icon name="mic" size={18} />
              )}
              {busy ? "Adding…" : "Add voice"}
            </button>
          </div>

          {done && (
            <div className="banner success field-wide" role="status">
              <Icon name="waveform" size={18} />
              <div className="banner-body">
                <span>
                  Added <strong>{done.name}</strong>
                  {done.replaced ? " (replaced existing)" : ""} — available to{" "}
                  {done.providers.join(" + ") || "cloning providers"}.
                </span>
                {done.notes.length > 0 && (
                  <span className="banner-hint">{done.notes.join(" · ")}</span>
                )}
              </div>
            </div>
          )}
          {error && (
            <div className="banner error field-wide" role="alert">
              <Icon name="alert" size={18} />
              <div className="banner-body">{error}</div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
