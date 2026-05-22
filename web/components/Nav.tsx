"use client";

import { Activity, FlaskConical, KeyRound, Plus, ShieldCheck, Terminal, TestTube2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/runs", label: "Runs", icon: Terminal },
  { href: "/tests", label: "Tests & Flows", icon: TestTube2 },
  { href: "/auth-profiles", label: "Auth Profiles", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: KeyRound },
];

// Routes that should render without the app shell (the sidebar).
const BARE_ROUTES = ["/login", "/signup", "/auth"];

export function Nav() {
  const pathname = usePathname();
  if (BARE_ROUTES.some((p) => pathname.startsWith(p))) return null;

  return (
    <aside className="sticky top-0 flex h-dvh w-56 shrink-0 flex-col border-r border-line bg-surface/60 backdrop-blur-md">
      {/* Brand */}
      <Link href="/" className="flex items-center gap-2.5 px-4 pb-5 pt-5">
        <span className="relative grid h-8 w-8 place-items-center rounded-lg border border-line bg-elevated">
          <FlaskConical className="h-4 w-4 text-accent" />
          <span className="absolute inset-0 rounded-lg shadow-glow" />
        </span>
        <span className="flex flex-col leading-none">
          <span className="text-sm font-semibold tracking-tight">QA Agent</span>
          <span className="eyebrow mt-1">autonomous testing</span>
        </span>
      </Link>

      <div className="px-3">
        <Link href="/runs/new" className="btn w-full">
          <Plus className="h-4 w-4" /> New run
        </Link>
      </div>

      <nav className="mt-5 flex flex-col gap-0.5 px-3">
        {links.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-all duration-150",
                active ? "bg-elevated text-ink" : "text-muted hover:bg-elevated/60 hover:text-ink"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1/2 h-4 -translate-y-1/2 rounded-r-full border-l-2 border-accent" />
              )}
              <Icon
                className={cn(
                  "h-4 w-4 transition-colors",
                  active ? "text-accent" : "text-faint group-hover:text-muted"
                )}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto px-4 pb-4">
        <div className="flex items-center gap-2 rounded-lg border border-line-soft bg-elevated/40 px-3 py-2 text-[11px] text-muted">
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" />
          <span className="font-mono">local · no-auth</span>
        </div>
      </div>
    </aside>
  );
}
