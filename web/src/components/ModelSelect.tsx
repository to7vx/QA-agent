import { useState } from "react";
import type { ProviderInfo } from "../types";

interface Props {
  provider: ProviderInfo | undefined;
  value: string;
  onChange: (model: string) => void;
  className?: string;
}

const CUSTOM = "__custom__";

/** Model picker: dropdown of the provider's catalog + a Custom… escape hatch. */
export default function ModelSelect({ provider, value, onChange, className = "" }: Props) {
  const models = provider?.models ?? [];
  const inCatalog = models.includes(value);
  const [custom, setCustom] = useState(!inCatalog && value !== "");

  const selectValue = custom ? CUSTOM : inCatalog ? value : models[0] ?? "";

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <select
        value={selectValue}
        onChange={(e) => {
          if (e.target.value === CUSTOM) {
            setCustom(true);
          } else {
            setCustom(false);
            onChange(e.target.value);
          }
        }}
        aria-label="Model"
        className="rounded-md border border-edge bg-raise px-2.5 py-1.5 font-mono text-xs text-fg focus:border-amber/60 focus:outline-none"
      >
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
            {m === provider?.default_model ? "  (default)" : ""}
          </option>
        ))}
        <option value={CUSTOM}>Custom…</option>
      </select>
      {custom && (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="model id"
          autoFocus
          spellCheck={false}
          className="w-44 rounded-md border border-edge bg-raise px-2.5 py-1.5 font-mono text-xs text-fg placeholder:text-dim focus:border-amber/60 focus:outline-none"
        />
      )}
    </div>
  );
}
