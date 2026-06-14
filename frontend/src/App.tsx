import { useEffect, useMemo, useState } from "react";
import { fetchVoices, generatePodcast } from "./api/client";
import { ResultPlayer } from "./components/ResultPlayer";
import { ScriptInput } from "./components/ScriptInput";
import { SpeakerConfig, speakerLabel } from "./components/SpeakerConfig";
import type { GenerateResult, SpeakerVoice, Voice } from "./types";

export default function App() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voicesError, setVoicesError] = useState<string | null>(null);

  const [numSpeakers, setNumSpeakers] = useState(2);
  const [speakerVoices, setSpeakerVoices] = useState<Record<string, SpeakerVoice>>({});
  const [scriptText, setScriptText] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);

  useEffect(() => {
    fetchVoices()
      .then(setVoices)
      .catch((err: Error) => setVoicesError(err.message));
  }, []);

  function handleVoiceChange(speaker: string, voiceId: string) {
    const voice = voices.find((v) => v.id === voiceId);
    setSpeakerVoices((prev) => ({
      ...prev,
      [speaker]: { provider: voice?.provider ?? "elevenlabs", voice_id: voiceId },
    }));
  }

  const activeSpeakers = useMemo(
    () => Array.from({ length: numSpeakers }, (_, i) => speakerLabel(i)),
    [numSpeakers],
  );

  const allVoicesAssigned = activeSpeakers.every(
    (s) => speakerVoices[s]?.voice_id,
  );
  const canGenerate =
    !loading && scriptText.trim().length > 0 && allVoicesAssigned;

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // Only send voice assignments for the active speakers.
      const speakers: Record<string, SpeakerVoice> = {};
      for (const s of activeSpeakers) speakers[s] = speakerVoices[s];

      const generated = await generatePodcast({
        script_text: scriptText,
        speakers,
      });
      setResult(generated);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="app-head">
        <h1>🎙️ Moodscape Podcasts</h1>
        <p>Paste a multi-speaker script, assign a voice to each speaker, generate the episode.</p>
      </header>

      {voicesError && (
        <div className="banner error">
          Couldn’t load voices: {voicesError}
          <span className="banner-hint">
            Check <code>ELEVENLABS_API_KEY</code> in <code>backend/.env</code>.
          </span>
        </div>
      )}

      <SpeakerConfig
        numSpeakers={numSpeakers}
        onNumSpeakersChange={setNumSpeakers}
        voices={voices}
        speakerVoices={speakerVoices}
        onVoiceChange={handleVoiceChange}
      />

      <ScriptInput value={scriptText} onChange={setScriptText} />

      <div className="actions">
        <button className="generate" onClick={handleGenerate} disabled={!canGenerate}>
          {loading ? "Generating…" : "Generate podcast"}
        </button>
        {!allVoicesAssigned && (
          <span className="hint">Assign a voice to every speaker first.</span>
        )}
      </div>

      {error && <div className="banner error">{error}</div>}
      {result && <ResultPlayer result={result} />}
    </div>
  );
}
