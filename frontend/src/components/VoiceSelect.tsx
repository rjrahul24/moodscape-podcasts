import type { Voice } from "../types";

interface Props {
  voices: Voice[];
  value: string;
  onChange: (voiceId: string) => void;
}

export function VoiceSelect({ voices, value, onChange }: Props) {
  return (
    <select
      className="voice-select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" disabled>
        {voices.length ? "Choose a voice…" : "No voices available"}
      </option>
      {voices.map((voice) => (
        <option key={`${voice.provider}:${voice.id}`} value={voice.id}>
          {voice.name}
          {voice.category ? ` (${voice.category})` : ""}
        </option>
      ))}
    </select>
  );
}
