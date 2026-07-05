import type { Flow } from "../types";

const priorityStyle: Record<string, string> = {
  high: "text-fail border-fail/40",
  medium: "text-amber border-amber/40",
  low: "text-mut border-edge",
};

export default function FlowCard({ flow }: { flow: Flow }) {
  return (
    <div className="rounded-lg border border-edge bg-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-display text-sm font-semibold">{flow.name}</h3>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] ${
            priorityStyle[flow.priority] ?? priorityStyle.low
          }`}
        >
          {flow.priority}
        </span>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-mut">{flow.description}</p>
      {flow.steps.length > 0 && (
        <ol className="mt-3 space-y-1 border-t border-edge/60 pt-3">
          {flow.steps.map((step, i) => (
            <li key={i} className="flex gap-2 text-xs text-mut">
              <span className="font-mono text-[10px] text-dim">{i + 1}</span>
              <span className="min-w-0">
                {step.description}
                {step.selector && (
                  <code className="ml-1.5 break-all font-mono text-[10px] text-heal/80">
                    {step.selector}
                  </code>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
      {flow.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {flow.tags.map((tag) => (
            <span key={tag} className="rounded bg-raise px-1.5 py-0.5 font-mono text-[10px] text-dim">
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
