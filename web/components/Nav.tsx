"use client";

import {
  Activity,
  FlaskConical,
  KeyRound,
  Menu,
  Plus,
  ShieldCheck,
  Terminal,
  TestTube2,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/runs", label: "Runs", icon: Terminal },
  { href: "/tests", label: "Tests & Flows", icon: TestTube2 },
  { href: "/auth-profiles", label: "Auth Profiles", icon: ShieldCheck },
  { href: "/settings", label: "Settings", icon: KeyRound },
];

// Routes that render without the app shell (the sidebar). Match the exact
// route or a sub-path (e.g. /auth/callback) — never a prefix like /auth that
// would also swallow sibling routes such as /auth-profiles.
const BARE_ROUTES = ["/login", "/signup", "/auth"];

function isBareRoute(pathname: string): boolean {
  return BARE_ROUTES.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setOpen(false), [pathname]);

  // Lock body scroll while the mobile drawer is open.
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (isBareRoute(pathname)) return null;

  return (
    <>
      {/* Mobile top bar (hidden on lg+) */}
      <header className="sticky top-0 z-40 flex items-center gap-3 border-b border-line bg-surface/80 px-4 py-3 backdrop-blur-md lg:hidden">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={open}
          className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-elevated/60 text-muted transition-colors hover:text-ink"
        >
          <Menu className="h-4 w-4" />
        </button>
        <Link href="/" className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg border border-line bg-elevated">
            <FlaskConical className="h-3.5 w-3.5 text-accent" />
          </span>
          <span className="text-sm font-semibold tracking-tight">QA Agent</span>
        </Link>
      </header>

      {/* Backdrop for the mobile drawer */}
      {open && (
        <button
          type="button"
          aria-label="Close navigation menu"
          tabIndex={-1}
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-40 cursor-default bg-black/60 backdrop-blur-sm lg:hidden"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-dvh w-64 shrink-0 flex-col border-r border-line",
          "bg-surface/95 backdrop-blur-md transition-transform duration-200 ease-out",
          "lg:sticky lg:top-0 lg:z-auto lg:w-56 lg:translate-x-0 lg:bg-surface/60",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        {/* Brand + mobile close */}
        <div className="flex items-center justify-between px-4 pb-5 pt-5">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="relative grid h-8 w-8 place-items-center rounded-lg border border-line bg-elevated">
              <FlaskConical className="h-4 w-4 text-accent" />
              <span className="absolute inset-0 rounded-lg shadow-glow" />
            </span>
            <span className="flex flex-col leading-none">
              <span className="text-sm font-semibold tracking-tight">QA Agent</span>
              <span className="eyebrow mt-1">autonomous testing</span>
            </span>
          </Link>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close navigation menu"
            className="grid h-8 w-8 place-items-center rounded-lg text-faint transition-colors hover:text-ink lg:hidden"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

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
                aria-current={active ? "page" : undefined}
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
    </>
  );
}
