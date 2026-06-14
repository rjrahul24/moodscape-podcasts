import type { GenerateRequest, GenerateResult, Voice } from "../types";

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export async function fetchVoices(): Promise<Voice[]> {
  const response = await fetch("/api/voices");
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
