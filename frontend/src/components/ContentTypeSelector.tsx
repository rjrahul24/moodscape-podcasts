import type { ContentType } from "../types";
import { Icon } from "./Icon";

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
        <Icon name="mic" size={18} />
        Podcast
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={value === "sleep_story"}
        className={value === "sleep_story" ? "toggle active" : "toggle"}
        onClick={() => onChange("sleep_story")}
        disabled={disabled}
      >
        <Icon name="moon" size={18} />
        Sleep Story
      </button>
    </div>
  );
}
