import type { PredictionMode } from "../lib/types";

export function PredictionModeToggle({ mode, onMode }: { mode: PredictionMode; onMode: (mode: PredictionMode) => void }) {
  return (
    <div className="predictionActions">
      <button className={mode === "demo" ? "active" : ""} onClick={() => onMode("demo")}>
        Show Demo Prediction
      </button>
      <button className={mode === "current" ? "active" : ""} onClick={() => onMode("current")}>
        Show Tomorrow Prediction
      </button>
    </div>
  );
}
