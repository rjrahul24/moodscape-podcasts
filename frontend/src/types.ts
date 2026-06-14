// Mirrors the backend pydantic models in app/core/models.py.

export interface Voice {
  id: string;
  name: string;
  provider: string;
  category?: string | null;
}

export interface SpeakerVoice {
  provider: string;
  voice_id: string;
}

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
