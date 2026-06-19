import { Icon } from "./Icon";

interface Props {
  value: string;
  onChange: (value: string) => void;
  pacing: boolean;
  onPacingChange: (pacing: boolean) => void;
}

const PLACEHOLDER = `[Speaker 1]: Welcome to the show! Today we're talking about deep-sea creatures.
[Speaker 2]: [excited] I've been looking forward to this. [pause:400] Let's dive in.
[Speaker 1]: Our first guest of the abyss is the anglerfish...`;

export function ScriptInput({ value, onChange, pacing, onPacingChange }: Props) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>
          <Icon name="script" /> Script
        </h2>
        <span className="hint">
          One turn per block, starting with <code>[Speaker N]:</code>
        </span>
      </div>
      <textarea
        className="script-area"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={PLACEHOLDER}
        spellCheck={false}
        rows={14}
      />
      <div className="script-foot">
        <label className="toggle">
          <input
            type="checkbox"
            checked={pacing}
            onChange={(e) => onPacingChange(e.target.checked)}
          />
          <span>Natural pacing</span>
        </label>
        <span className="hint">
          Adds sentence pauses &amp; varied timing. Inline tags:{" "}
          <code>[pause:600]</code> silence,{" "}
          <code>[breath]</code> <code>[deep_breath]</code> <code>[sigh]</code>{" "}
          breaths,{" "}
          <code>[excited]</code> <code>[calm]</code> <code>[soothing]</code>{" "}
          <code>[reflective]</code> <code>[warm]</code> <code>[sad]</code>{" "}
          <code>[whispering]</code> tone.
        </span>
      </div>
    </section>
  );
}
