import type { JobProgress } from "../types";
import { Icon } from "./Icon";

interface Props {
  progress: JobProgress;
}

export function ProgressBar({ progress }: Props) {
  const pct = Math.round(progress.progress * 100);
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>
          <Icon name="loader" className="spin" /> Generating…
        </h2>
        <span className="hint">{progress.step}</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="progress-meta">
        <span className="progress-pct">{pct}%</span>
        {progress.chunks_total > 0 && (
          <span>
            · {progress.chunks_done}/{progress.chunks_total} chunks
          </span>
        )}
      </div>
    </section>
  );
}
