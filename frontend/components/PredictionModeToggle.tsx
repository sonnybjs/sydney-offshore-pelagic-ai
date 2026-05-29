import type { PredictionMode } from "../lib/types";

export function PredictionModeToggle({
  mode,
  onMode,
  onToday,
  onTomorrow,
  selectedDate,
  todayDate,
  tomorrowDate,
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
    <div className="predictionActions">
      <button className={mode === "demo" ? "active" : ""} onClick={() => onMode("demo")}>
        Show Demo Prediction
      </button>
      <button className={mode === "current" && selectedDate === todayDate ? "active" : ""} onClick={onToday || (() => onMode("current"))}>
        Show Today Prediction
      </button>
      <button className={mode === "current" && selectedDate === tomorrowDate ? "active" : ""} onClick={onTomorrow || (() => onMode("current"))}>
        Show Tomorrow Prediction
      </button>
    </div>
  );
}
