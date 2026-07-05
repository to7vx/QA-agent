import { NavLink, Route, Routes } from "react-router-dom";
import { History, Play, Settings as SettingsIcon } from "lucide-react";
import NewRun from "./pages/NewRun";
import RunView from "./pages/RunView";
import HistoryPage from "./pages/History";
import SettingsPage from "./pages/Settings";

const navItems = [
  { to: "/", label: "New run", icon: Play },
  { to: "/history", label: "History", icon: History },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function App() {
  return (
    <div className="flex min-h-screen bg-ink text-fg">
      <aside className="flex w-52 shrink-0 flex-col border-r border-edge bg-panel/60">
        <div className="px-5 pb-6 pt-6">
          <div className="font-display text-lg font-700 tracking-tight">
            qa<span className="text-amber">-</span>agent
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-dim">
            autonomous web QA
          </div>
        </div>
        <nav className="flex flex-col gap-1 px-3">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-raise font-medium text-fg"
                    : "text-mut hover:bg-raise/60 hover:text-fg"
                }`
              }
            >
              <Icon size={15} strokeWidth={2} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4 font-mono text-[10px] leading-relaxed text-dim">
          runs locally
          <br />
          127.0.0.1:8899
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<NewRun />} />
          <Route path="/runs/:runId" element={<RunView />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
