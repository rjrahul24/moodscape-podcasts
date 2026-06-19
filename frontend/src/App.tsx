import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchVoices } from "./api/client";
import { fetchAmbient, runJob } from "./api/jobs";
import { AddVoice } from "./components/AddVoice";
import { ContentTypeSelector } from "./components/ContentTypeSelector";
import { Icon } from "./components/Icon";
import { ProgressBar } from "./components/ProgressBar";
import { ResultPlayer } from "./components/ResultPlayer";
import { ScriptInput } from "./components/ScriptInput";
import { SleepStoryConfig } from "./components/SleepStoryConfig";
import { SpeakerConfig, speakerLabel } from "./components/SpeakerConfig";
import {
  ELEVENLABS_MODELS,
  type AmbientBed,
  type ContentType,
  type GenerateResult,
  type JobProgress,
  type ProviderVoices,
  type SpeakerVoice,
} from "./types";

export default function App() {
  const [contentType, setContentType] = useState<ContentType>("podcast");
  const [providerVoices, setProviderVoices] = useState<ProviderVoices[]>([]);
  const [voicesError, setVoicesError] = useState<string | null>(null);
  const [ambientBeds, setAmbientBeds] = useState<AmbientBed[]>([]);

  // Podcast state
  const [numSpeakers, setNumSpeakers] = useState(2);
  const [speakerVoices, setSpeakerVoices] = useState<Record<string, SpeakerVoice>>({});
  const [scriptText, setScriptText] = useState("");
  const [pacing, setPacing] = useState(true);

  // Sleep-story state
  const [sleepProvider, setSleepProvider] = useState("kokoro");
  const [sleepVoiceId, setSleepVoiceId] = useState("");
  const [sleepModel, setSleepModel] = useState(ELEVENLABS_MODELS[0].id);
  const [sleepSpeed, setSleepSpeed] = useState(0.85);
  const [sleepPauseMs, setSleepPauseMs] = useState(900);
  const [sleepRamp, setSleepRamp] = useState(true);
  const [sleepAmbient, setSleepAmbient] = useState("");
  const [sleepStyle, setSleepStyle] = useState("");
  const [proseText, setProseText] = useState("");

  // Shared job state
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResult | null>(null);

  const loadVoices = useCallback(() => {
    fetchVoices()
      .then((groups) => {
        setProviderVoices(groups);
        setVoicesError(null);
      })
      .catch((err: Error) => setVoicesError(err.message));
  }, []);

  useEffect(() => {
    loadVoices();
    fetchAmbient()
      .then(setAmbientBeds)
      .catch(() => setAmbientBeds([]));
  }, [loadVoices]);

  const defaultProvider = providerVoices[0]?.provider ?? "elevenlabs";

  function handleProviderChange(speaker: string, provider: string) {
    setSpeakerVoices((prev) => ({
      ...prev,
      [speaker]: {
        provider,
        voice_id: "",
        model_id: provider === "elevenlabs" ? ELEVENLABS_MODELS[0].id : undefined,
      },
    }));
  }

  function handleVoiceChange(speaker: string, voiceId: string) {
    setSpeakerVoices((prev) => ({
      ...prev,
      [speaker]: {
        provider: prev[speaker]?.provider ?? defaultProvider,
        voice_id: voiceId,
        model_id: prev[speaker]?.model_id,
      },
    }));
  }

  function handleModelChange(speaker: string, modelId: string) {
    setSpeakerVoices((prev) => ({
      ...prev,
      [speaker]: {
        provider: prev[speaker]?.provider ?? defaultProvider,
        voice_id: prev[speaker]?.voice_id ?? "",
        model_id: modelId,
      },
    }));
  }

  function handleSleepProviderChange(provider: string) {
    setSleepProvider(provider);
    setSleepVoiceId(""); // voices are provider-specific
  }

  const activeSpeakers = useMemo(
    () => Array.from({ length: numSpeakers }, (_, i) => speakerLabel(i)),
    [numSpeakers],
  );

  const podcastReady =
    scriptText.trim().length > 0 &&
    activeSpeakers.every((s) => speakerVoices[s]?.voice_id);
  const sleepReady = proseText.trim().length > 0 && sleepVoiceId.length > 0;
  const canGenerate =
    !loading && (contentType === "podcast" ? podcastReady : sleepReady);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    setResult(null);
    setProgress({
      status: "queued",
      progress: 0,
      step: "Queued",
      chunks_total: 0,
      chunks_done: 0,
    });
    try {
      if (contentType === "podcast") {
        const speakers: Record<string, SpeakerVoice> = {};
        for (const s of activeSpeakers) speakers[s] = speakerVoices[s];
        const view = await runJob(
          { kind: "podcast", script_text: scriptText, speakers, pacing },
          setProgress,
        );
        setResult(view.result);
      } else {
        const view = await runJob(
          {
            kind: "sleep_story",
            prose_text: proseText,
            provider: sleepProvider,
            voice_id: sleepVoiceId,
            model_id: sleepProvider === "elevenlabs" ? sleepModel : null,
            speed: sleepSpeed,
            pause_ms: sleepPauseMs,
            ramp: sleepRamp,
            ambient_bed: sleepAmbient || null,
            style_prompt:
              sleepProvider === "cosyvoice" && sleepStyle.trim()
                ? sleepStyle.trim()
                : null,
          },
          setProgress,
        );
        setResult(view.result);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }

  const isSleep = contentType === "sleep_story";

  return (
    <div className="app">
      <header className="app-head">
        <span className="app-mark" aria-hidden="true">
          <Icon name="waveform" size={26} />
        </span>
        <div>
          <h1>Moodscape Studio</h1>
          <p>
            {isSleep
              ? "Paste a full sleep story, pick a calming voice, and render a sleep-ready episode."
              : "Paste a multi-speaker script, assign a model + voice to each speaker, generate the episode."}
          </p>
        </div>
      </header>

      <ContentTypeSelector
        value={contentType}
        onChange={setContentType}
        disabled={loading}
      />

      {voicesError && (
        <div className="banner error" role="alert">
          <Icon name="alert" size={18} />
          <div className="banner-body">
            <span>Couldn’t load voices: {voicesError}</span>
            <span className="banner-hint">Is the backend running?</span>
          </div>
        </div>
      )}

      <AddVoice onAdded={loadVoices} />

      {isSleep ? (
        <SleepStoryConfig
          providerVoices={providerVoices}
          ambientBeds={ambientBeds}
          provider={sleepProvider}
          voiceId={sleepVoiceId}
          modelId={sleepModel}
          speed={sleepSpeed}
          pauseMs={sleepPauseMs}
          ramp={sleepRamp}
          ambientBed={sleepAmbient}
          stylePrompt={sleepStyle}
          proseText={proseText}
          onProviderChange={handleSleepProviderChange}
          onVoiceChange={setSleepVoiceId}
          onModelChange={setSleepModel}
          onSpeedChange={setSleepSpeed}
          onPauseChange={setSleepPauseMs}
          onRampChange={setSleepRamp}
          onAmbientChange={setSleepAmbient}
          onStyleChange={setSleepStyle}
          onProseChange={setProseText}
        />
      ) : (
        <>
          <SpeakerConfig
            numSpeakers={numSpeakers}
            onNumSpeakersChange={setNumSpeakers}
            providerVoices={providerVoices}
            speakerVoices={speakerVoices}
            onProviderChange={handleProviderChange}
            onVoiceChange={handleVoiceChange}
            onModelChange={handleModelChange}
          />
          <ScriptInput
            value={scriptText}
            onChange={setScriptText}
            pacing={pacing}
            onPacingChange={setPacing}
          />
        </>
      )}

      <div className="actions">
        <button className="generate" onClick={handleGenerate} disabled={!canGenerate}>
          {loading ? (
            <Icon name="loader" size={18} className="spin" />
          ) : (
            <Icon name={isSleep ? "moon" : "sparkles"} size={18} />
          )}
          {loading ? "Generating…" : isSleep ? "Generate sleep story" : "Generate podcast"}
        </button>
        {!canGenerate && !loading && (
          <span className="hint">
            {isSleep
              ? "Pick a voice and paste your story first."
              : "Assign a model + voice to every speaker first."}
          </span>
        )}
      </div>

      {loading && progress && <ProgressBar progress={progress} />}
      {error && (
        <div className="banner error" role="alert">
          <Icon name="alert" size={18} />
          <div className="banner-body">{error}</div>
        </div>
      )}
      {result && <ResultPlayer result={result} />}
    </div>
  );
}
