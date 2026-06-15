import type { JobProgress } from "../types";

interface Props {
  progress: JobProgress;
}

export function ProgressBar({ progress }: Props) {
  const pct = Math.round(progress.progress * 100);
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Generating…</h2>
        <span className="hint">{progress.step}</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="hint">
        {pct}%
        {progress.chunks_total > 0
          ? ` · ${progress.chunks_done}/${progress.chunks_total} chunks`
          : ""}
      </span>
    </section>
  );
}
