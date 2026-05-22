"use client";

import { AlertTriangle, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red, destructive styling for the confirm button. */
  destructive?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Accessible confirmation modal: focus moves to the confirm button on open,
 * Escape and backdrop click cancel, and a scrim isolates the foreground.
 * Used to gate destructive actions (delete key, delete auth profile).
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  pending = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !pending) onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, pending, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      {/* Scrim */}
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={() => !pending && onCancel()}
        className="absolute inset-0 cursor-default bg-black/60 backdrop-blur-sm animate-fade-up"
      />
      <div className="relative w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-xl animate-fade-up">
        <div className="flex items-start gap-3">
          {destructive && (
            <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-bad/25 bg-bad/10">
              <AlertTriangle className="h-4 w-4 text-bad" />
            </span>
          )}
          <div className="min-w-0">
            <h2 id="confirm-title" className="text-sm font-semibold tracking-tight text-ink">
              {title}
            </h2>
            {description && <div className="mt-1.5 text-[13px] text-muted">{description}</div>}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onCancel} disabled={pending}>
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className={cn(
              "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px]",
              "font-semibold tracking-tight transition-all duration-150 active:scale-[0.98]",
              "disabled:cursor-not-allowed disabled:opacity-50",
              destructive
                ? "bg-bad text-[#1a0606] hover:brightness-110"
                : "bg-accent text-[#04130d] hover:brightness-110"
            )}
          >
            {pending && <Loader2 className="h-4 w-4 animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
