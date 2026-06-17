import { ELEVENLABS_MODELS, type ProviderVoices, type SpeakerVoice } from "../types";
import { Icon } from "./Icon";
import { VoiceSelect } from "./VoiceSelect";

interface Props {
  numSpeakers: number;
  onNumSpeakersChange: (n: number) => void;
  providerVoices: ProviderVoices[];
  speakerVoices: Record<string, SpeakerVoice>;
  onProviderChange: (speaker: string, provider: string) => void;
  onVoiceChange: (speaker: string, voiceId: string) => void;
  onModelChange: (speaker: string, modelId: string) => void;
  maxSpeakers?: number;
}

export function speakerLabel(i: number): string {
  return `Speaker ${i + 1}`;
}

const PROVIDER_LABELS: Record<string, string> = {
  elevenlabs: "ElevenLabs",
  kokoro: "Kokoro",
  f5: "F5",
};

function providerLabel(name: string): string {
  return PROVIDER_LABELS[name] ?? name;
}

export function SpeakerConfig({
  numSpeakers,
  onNumSpeakersChange,
  providerVoices,
  speakerVoices,
  onProviderChange,
  onVoiceChange,
  onModelChange,
  maxSpeakers = 6,
}: Props) {
  const speakers = Array.from({ length: numSpeakers }, (_, i) => speakerLabel(i));

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>
          <Icon name="users" /> Speakers
        </h2>
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
        {speakers.map((speaker) => {
          const selectedProvider = speakerVoices[speaker]?.provider ?? "";
          const group = providerVoices.find((p) => p.provider === selectedProvider);
          const isElevenLabs = selectedProvider === "elevenlabs";
          const selectedModel =
            speakerVoices[speaker]?.model_id ?? ELEVENLABS_MODELS[0].id;
          return (
            <div key={speaker} className="speaker-row">
              <span className="speaker-tag">[{speaker}]</span>

              <select
                className="provider-select"
                value={selectedProvider}
                onChange={(e) => onProviderChange(speaker, e.target.value)}
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

              {isElevenLabs && (
                <select
                  className="provider-select"
                  value={selectedModel}
                  onChange={(e) => onModelChange(speaker, e.target.value)}
                  title="ElevenLabs model"
                >
                  {ELEVENLABS_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              )}

              <div className="voice-cell">
                <VoiceSelect
                  voices={group?.voices ?? []}
                  value={speakerVoices[speaker]?.voice_id ?? ""}
                  onChange={(voiceId) => onVoiceChange(speaker, voiceId)}
                />
                {group?.error && (
                  <span className="voice-error">{group.error}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
