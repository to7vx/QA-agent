import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function statusColor(status: string): string {
  switch (status) {
    case "succeeded":
    case "passed":
      return "text-good";
    case "failed":
    case "error":
      return "text-bad";
    case "running":
    case "queued":
      return "text-accent";
    default:
      return "text-muted";
  }
}
