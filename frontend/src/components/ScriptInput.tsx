interface Props {
  value: string;
  onChange: (value: string) => void;
}

const PLACEHOLDER = `[Speaker 1]: Welcome to the show! Today we're talking about deep-sea creatures.
[Speaker 2]: I've been looking forward to this. Let's dive in.
[Speaker 1]: Our first guest of the abyss is the anglerfish...`;

export function ScriptInput({ value, onChange }: Props) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Script</h2>
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
    </section>
  );
}
