import type { GenerateResult } from "../types";
import { Icon } from "./Icon";

interface Props {
  result: GenerateResult;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatBytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

export function ResultPlayer({ result }: Props) {
  // Prefer a playable format for the inline player (mp3/wav both work in browsers).
  const playable = result.files[0];

  return (
    <section className="panel result">
      <div className="panel-head">
        <h2>
          <Icon name="disc" /> Episode
        </h2>
        <span className="hint">{formatDuration(result.duration_ms)} · {result.segments.length} turns</span>
      </div>

      {playable && (
        <audio className="player" controls src={playable.download_url} />
      )}

      <ul className="downloads">
        {result.files.map((file) => (
          <li key={file.filename}>
            <a href={file.download_url} download={file.filename}>
              <Icon name="download" size={16} />
              {file.filename}
            </a>
            <span className="meta">
              {file.format.toUpperCase()} · {formatBytes(file.size_bytes)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
