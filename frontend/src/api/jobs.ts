import type {
  AmbientBed,
  JobCreated,
  JobProgress,
  JobRequest,
  JobView,
  SeriesInfo,
} from "../types";
import { parseError } from "./client";

export async function fetchAmbient(): Promise<AmbientBed[]> {
  const response = await fetch("/api/ambient");
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function fetchSeries(): Promise<SeriesInfo[]> {
  const response = await fetch("/api/series");
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function createJob(request: JobRequest): Promise<JobCreated> {
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

export async function getJob(jobId: string): Promise<JobView> {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}

/**
 * Create a job and follow it to completion over SSE, reporting progress.
 * Resolves with the finished {@link JobView}; rejects on failure. Falls back to
 * a single poll if the event stream errors.
 */
export async function runJob(
  request: JobRequest,
  onProgress: (progress: JobProgress) => void,
): Promise<JobView> {
  const created = await createJob(request);

  return new Promise<JobView>((resolve, reject) => {
    const source = new EventSource(`/api/jobs/${created.job_id}/events`);

    source.addEventListener("progress", (event) => {
      try {
        onProgress(JSON.parse((event as MessageEvent).data));
      } catch {
        // ignore malformed progress frames
      }
    });

    source.addEventListener("done", (event) => {
      source.close();
      try {
        const view: JobView = JSON.parse((event as MessageEvent).data);
        if (view.progress.status === "failed") {
          reject(new Error(view.progress.detail ?? "Generation failed."));
        } else {
          resolve(view);
        }
      } catch (err) {
        reject(err as Error);
      }
    });

    source.onerror = () => {
      // The stream dropped before a terminal event — poll once to settle.
      source.close();
      getJob(created.job_id)
        .then((view) => {
          if (view.progress.status === "succeeded") resolve(view);
          else if (view.progress.status === "failed")
            reject(new Error(view.progress.detail ?? "Generation failed."));
          else reject(new Error("Lost connection to the generation job."));
        })
        .catch(reject);
    };
  });
}
