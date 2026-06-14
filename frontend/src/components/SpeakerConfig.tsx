import type { SpeakerVoice, Voice } from "../types";
import { VoiceSelect } from "./VoiceSelect";

interface Props {
  numSpeakers: number;
  onNumSpeakersChange: (n: number) => void;
  voices: Voice[];
  speakerVoices: Record<string, SpeakerVoice>;
  onVoiceChange: (speaker: string, voiceId: string) => void;
  maxSpeakers?: number;
}

export function speakerLabel(i: number): string {
  return `Speaker ${i + 1}`;
}

export function SpeakerConfig({
  numSpeakers,
  onNumSpeakersChange,
  voices,
  speakerVoices,
  onVoiceChange,
  maxSpeakers = 6,
}: Props) {
  const speakers = Array.from({ length: numSpeakers }, (_, i) => speakerLabel(i));

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Speakers</h2>
        <label className="num-speakers">
          How many?
          <select
            value={numSpeakers}
            onChange={(e) => onNumSpeakersChange(Number(e.target.value))}
          >
            {Array.from({ length: maxSpeakers }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="speaker-rows">
        {speakers.map((speaker) => (
          <div key={speaker} className="speaker-row">
            <span className="speaker-tag">[{speaker}]</span>
            <VoiceSelect
              voices={voices}
              value={speakerVoices[speaker]?.voice_id ?? ""}
              onChange={(voiceId) => onVoiceChange(speaker, voiceId)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}
