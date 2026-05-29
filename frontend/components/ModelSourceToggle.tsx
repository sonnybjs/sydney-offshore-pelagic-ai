import type { ModelSource } from "../lib/types";

export function ModelSourceToggle({ modelSource, onModelSource }: { modelSource: ModelSource; onModelSource: (source: ModelSource) => void }) {
  return (
    <div className="predictionActions modelSourceActions">
      <button className={modelSource === "scikit_learn" ? "active" : ""} onClick={() => onModelSource("scikit_learn")}>
        Scikit-learn
      </button>
      <button className={modelSource === "deep_learning" ? "active" : ""} onClick={() => onModelSource("deep_learning")}>
        Deep Learning
      </button>
    </div>
  );
}
