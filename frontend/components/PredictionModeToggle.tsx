import type { PredictionMode } from "../lib/types";

const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");
const btn = (active: boolean) => cn(
  "border rounded-btn px-3 py-2.5 cursor-pointer text-[var(--text)] text-[15px] transition-colors text-left",
  active ? "border-[var(--accent)] bg-[var(--btn-selected)]" : "border-[var(--line)] bg-[var(--btn-bg)]"
);

export function PredictionModeToggle({
  mode, onMode, onToday, onTomorrow, selectedDate, todayDate, tomorrowDate,
}: {
  mode: PredictionMode;
  onMode: (mode: PredictionMode) => void;
  onToday?: () => void;
  onTomorrow?: () => void;
  selectedDate?: string | null;
  todayDate?: string | null;
  tomorrowDate?: string | null;
}) {
  return (
    <div className="grid gap-2">
      <button className={btn(mode === "demo")} onClick={() => onMode("demo")}>Show Demo Prediction</button>
      <button className={btn(mode === "current" && selectedDate === todayDate)} onClick={onToday || (() => onMode("current"))}>Show Today Prediction</button>
      <button className={btn(mode === "current" && selectedDate === tomorrowDate)} onClick={onTomorrow || (() => onMode("current"))}>Show Tomorrow Prediction</button>
    </div>
  );
}
