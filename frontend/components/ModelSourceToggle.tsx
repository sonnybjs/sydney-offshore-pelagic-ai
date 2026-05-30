import type { ModelSource } from "../lib/types";

const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");
const btn = (active: boolean) => cn(
  "border rounded-btn px-3 py-2.5 cursor-pointer text-[var(--text)] text-[15px] transition-colors text-center",
  active ? "border-[var(--accent)] bg-[var(--btn-selected)]" : "border-[var(--line)] bg-[var(--btn-bg)]"
);

export function ModelSourceToggle({ modelSource, onModelSource }: { modelSource: ModelSource; onModelSource: (source: ModelSource) => void }) {
  return (
    <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
      <h2 className="m-0 mb-3 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0]">Model Source</h2>
      <div className="grid grid-cols-2 gap-2">
        <button className={btn(modelSource === "scikit_learn")} onClick={() => onModelSource("scikit_learn")}>Scikit-learn</button>
        <button className={btn(modelSource === "deep_learning")} onClick={() => onModelSource("deep_learning")}>Deep Learning</button>
      </div>
      <p className="mt-2.5 text-[var(--muted)] text-xs">
        {modelSource === "deep_learning" ? "Experimental PyTorch MLP sidecar model." : "Original scikit-learn selected model output."}
      </p>
    </section>
  );
}
