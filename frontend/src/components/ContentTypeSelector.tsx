import type { ContentType } from "../types";

interface Props {
  value: ContentType;
  onChange: (value: ContentType) => void;
  disabled?: boolean;
}

export function ContentTypeSelector({ value, onChange, disabled }: Props) {
  return (
    <div className="content-toggle" role="tablist" aria-label="Content type">
      <button
        type="button"
        role="tab"
        aria-selected={value === "podcast"}
        className={value === "podcast" ? "toggle active" : "toggle"}
        onClick={() => onChange("podcast")}
        disabled={disabled}
      >
        🎙️ Podcast
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={value === "sleep_story"}
        className={value === "sleep_story" ? "toggle active" : "toggle"}
        onClick={() => onChange("sleep_story")}
        disabled={disabled}
      >
        🌙 Sleep Story
      </button>
    </div>
  );
}
