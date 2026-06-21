import {
  type AmbientBed,
  type ProviderVoices,
} from "../types";
import { Icon } from "./Icon";
import { VoiceSelect } from "./VoiceSelect";

interface Props {
  providerVoices: ProviderVoices[];
  ambientBeds: AmbientBed[];
  provider: string;
  voiceId: string;
  speed: number;
  pauseMs: number;
  ramp: boolean;
  ambientBed: string;
  proseText: string;
  onProviderChange: (provider: string) => void;
  onVoiceChange: (voiceId: string) => void;
  onSpeedChange: (speed: number) => void;
  onPauseChange: (pauseMs: number) => void;
  onRampChange: (ramp: boolean) => void;
  onAmbientChange: (slug: string) => void;
  onProseChange: (text: string) => void;
}

const PROVIDER_LABELS: Record<string, string> = {
  kokoro: "Kokoro",
  f5: "F5",
};

const PLACEHOLDER = `Paste your full sleep story here as plain prose — no speaker tags needed.

The old lighthouse stood at the edge of the bay, its lamp turning slowly through the mist. Down below, the tide breathed in and out against the smooth grey stones...`;

function providerLabel(name: string): string {
  return PROVIDER_LABELS[name] ?? name;
}

function durationGuidance(words: number): string {
  if (words === 0) return "≈ 110 words per minute when narrated";
  const minutes = Math.round(words / 105);
  return `≈ ${minutes} min at a calm pace`;
}

export function SleepStoryConfig({
  providerVoices,
  ambientBeds,
  provider,
  voiceId,
  speed,
  pauseMs,
  ramp,
  ambientBed,
  proseText,
  onProviderChange,
  onVoiceChange,
  onSpeedChange,
  onPauseChange,
  onRampChange,
  onAmbientChange,
  onProseChange,
}: Props) {
  const group = providerVoices.find((p) => p.provider === provider);
  const wordCount = proseText.trim() ? proseText.trim().split(/\s+/).length : 0;

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>
            <Icon name="sliders" /> Narration
          </h2>
          <span className="hint">One voice, calming pace</span>
        </div>

        <div className="sleep-grid">
          <label className="field">
            <span className="field-label">Model</span>
            <select
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
            >
              <option value="" disabled>
                Model…
              </option>
              {providerVoices.map((p) => (
                <option key={p.provider} value={p.provider}>
                  {providerLabel(p.provider)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field-label">Voice</span>
            <VoiceSelect
              voices={group?.voices ?? []}
              value={voiceId}
              onChange={onVoiceChange}
            />
            {group?.error && <span className="voice-error">{group.error}</span>}
          </label>

          <label className="field">
            <span className="field-label">
              Speed <span className="field-value">{speed.toFixed(2)}×</span>
            </span>
            <input
              type="range"
              min={0.6}
              max={1.1}
              step={0.05}
              value={speed}
              onChange={(e) => onSpeedChange(Number(e.target.value))}
            />
          </label>

          <label className="field">
            <span className="field-label">
              Pause between sentences{" "}
              <span className="field-value">{(pauseMs / 1000).toFixed(1)}s</span>
            </span>
            <input
              type="range"
              min={0}
              max={3000}
              step={100}
              value={pauseMs}
              onChange={(e) => onPauseChange(Number(e.target.value))}
            />
          </label>

          <label className="field field-wide checkbox-field">
            <input
              type="checkbox"
              checked={ramp}
              onChange={(e) => onRampChange(e.target.checked)}
            />
            <span className="field-label">
              Progressive ramp-down
              <span className="hint">
                Gently slow the pace and lengthen pauses toward the end, easing
                the listener into sleep.
              </span>
            </span>
          </label>

          <label className="field field-wide">
            <span className="field-label">Ambient bed</span>
            <select
              value={ambientBed}
              onChange={(e) => onAmbientChange(e.target.value)}
            >
              <option value="">None</option>
              {ambientBeds.map((bed) => (
                <option key={bed.id} value={bed.id}>
                  {bed.name}
                </option>
              ))}
            </select>
            {ambientBeds.length === 0 && (
              <span className="hint">
                Add files to <code>assets/ambient/</code> to offer beds.
              </span>
            )}
          </label>

        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>
            <Icon name="book" /> Story
          </h2>
          <span className="hint">
            {wordCount} words · {durationGuidance(wordCount)}
          </span>
        </div>
        <textarea
          className="script-area"
          value={proseText}
          onChange={(e) => onProseChange(e.target.value)}
          placeholder={PLACEHOLDER}
          spellCheck
          rows={16}
        />
        <span className="hint">
          A 30-min story is ~2,700–3,300 words; 45 min is ~4,000–5,000.
        </span>
      </section>
    </>
  );
}
