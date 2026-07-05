import { Check } from "lucide-react";

const STAGES = [
  { id: "explore", label: "Explore", hint: "reading the page" },
  { id: "generate", label: "Generate", hint: "writing tests" },
  { id: "execute", label: "Execute", hint: "running pytest" },
  { id: "report", label: "Report", hint: "summarizing" },
];

interface Props {
  active: string | null;
  done: string[];
  failed?: boolean;
}

/**
 * The conveyor: four stage nodes on a rail. The segment feeding the active
 * stage flows (animated dashes); the active node pulses amber.
 */
export default function PipelineStepper({ active, done, failed = false }: Props) {
  const activeIdx = active ? STAGES.findIndex((s) => s.id === active) : -1;

  return (
    <div className="flex items-start" role="list" aria-label="Pipeline stages">
      {STAGES.map((stage, i) => {
        const isDone = done.includes(stage.id);
        const isActive = stage.id === active;
        const reached = isDone || isActive;
        return (
          <div key={stage.id} role="listitem" className="flex flex-1 items-start last:flex-none">
            <div className="flex w-24 flex-col items-center gap-2">
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-full border font-mono text-xs transition-colors ${
                  isActive
                    ? "pulse-node border-amber bg-amber/15 text-amber"
                    : isDone
                      ? "border-pass/50 bg-pass/10 text-pass"
                      : failed && !reached
                        ? "border-edge bg-panel text-dim"
                        : "border-edge bg-panel text-dim"
                }`}
              >
                {isDone ? <Check size={15} strokeWidth={2.5} /> : i + 1}
              </div>
              <div className="text-center">
                <div
                  className={`font-display text-xs font-medium ${
                    reached ? "text-fg" : "text-dim"
                  }`}
                >
                  {stage.label}
                </div>
                {isActive && (
                  <div className="mt-0.5 font-mono text-[10px] text-amber/80">
                    {stage.hint}…
                  </div>
                )}
              </div>
            </div>
            {i < STAGES.length - 1 && (
              <svg className="mt-[17px] h-0.5 min-w-6 flex-1" aria-hidden="true">
                <line
                  x1="0"
                  y1="1"
                  x2="100%"
                  y2="1"
                  strokeWidth="2"
                  stroke={
                    i < activeIdx || done.includes(STAGES[i + 1].id)
                      ? "var(--color-pass)"
                      : i === activeIdx
                        ? "var(--color-amber)"
                        : "var(--color-edge)"
                  }
                  className={i === activeIdx ? "conveyor" : undefined}
                />
              </svg>
            )}
          </div>
        );
      })}
    </div>
  );
}
