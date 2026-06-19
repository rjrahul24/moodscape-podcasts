import type {
  GenerateRequest,
  GenerateResult,
  ProviderVoices,
  ReferenceVoiceCreated,
} from "../types";

export async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export async function fetchVoices(): Promise<ProviderVoices[]> {
  const response = await fetch("/api/voices");
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function uploadReferenceVoice(input: {
  name: string;
  audio: File;
  transcript?: string;
}): Promise<ReferenceVoiceCreated> {
  const form = new FormData();
  form.append("name", input.name);
  form.append("audio", input.audio);
  if (input.transcript?.trim()) form.append("transcript", input.transcript.trim());
  const response = await fetch("/api/voices/reference", {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function generatePodcast(
  request: GenerateRequest,
): Promise<GenerateResult> {
  const response = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}
