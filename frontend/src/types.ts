// Mirrors the backend pydantic models in app/core/models.py.

export interface Voice {
  id: string;
  name: string;
  provider: string;
  category?: string | null;
}

export interface ProviderVoices {
  provider: string;
  voices: Voice[];
  error?: string | null;
}

export interface SpeakerVoice {
  provider: string;
  voice_id: string;
  // ElevenLabs model override (v2 vs v3); ignored by other providers.
  model_id?: string | null;
}

// ElevenLabs models the UI lets you pick. v3 is more expressive (inline audio
// tags + discrete stability); v2 has the best text normalization.
export const ELEVENLABS_MODELS: { id: string; label: string }[] = [
  { id: "eleven_multilingual_v2", label: "Multilingual v2" },
  { id: "eleven_v3", label: "v3 (expressive)" },
];

export interface GenerateRequest {
  script_text: string;
  speakers: Record<string, SpeakerVoice>;
  output_format?: string | null;
  gap_ms?: number | null;
}

export interface SegmentInfo {
  index: number;
  speaker: string;
  voice_id: string;
  provider: string;
  duration_ms: number;
}

export interface GeneratedFile {
  filename: string;
  format: string;
  download_url: string;
  size_bytes: number;
}

export interface GenerateResult {
  job_id: string;
  duration_ms: number;
  segments: SegmentInfo[];
  files: GeneratedFile[];
}

// ── Async jobs (POST /api/jobs) ──────────────────────────────────────────────

export type ContentType = "podcast" | "sleep_story";

export interface PodcastJobRequest {
  kind: "podcast";
  script_text: string;
  speakers: Record<string, SpeakerVoice>;
  output_format?: string | null;
  gap_ms?: number | null;
  pacing?: boolean; // conversational pacing + tone tags (default true)
}

export interface SleepStoryJobRequest {
  kind: "sleep_story";
  prose_text: string;
  provider: string;
  voice_id: string;
  model_id?: string | null; // ElevenLabs model override (v2/v3); else ignored
  speed?: number | null;
  pause_ms?: number | null;
  ambient_bed?: string | null;
}

export type JobRequest = PodcastJobRequest | SleepStoryJobRequest;

export interface JobCreated {
  job_id: string;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface JobProgress {
  status: JobStatus;
  progress: number; // 0.0 .. 1.0
  step: string;
  chunks_total: number;
  chunks_done: number;
  detail?: string | null;
}

export interface JobView {
  job_id: string;
  kind: ContentType;
  progress: JobProgress;
  result: GenerateResult | null;
}

export interface AmbientBed {
  id: string;
  name: string;
}
