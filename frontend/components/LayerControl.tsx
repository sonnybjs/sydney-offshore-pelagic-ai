import type { LayerState } from "../lib/types";

const labels: Array<[keyof LayerState, string]> = [
  ["heatmap", "Habitat heatmap"],
  ["hotspots", "Recommendation points"],
  ["fronts", "SST front proxy"],
  ["currents", "Current arrows"],
  ["pois", "POI markers"],
  ["shelf", "Shelf/depth markers"],
];

export function LayerControl({ layers, onToggle }: { layers: LayerState; onToggle: (key: keyof LayerState) => void }) {
  return (
    <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
      <h2 className="m-0 mb-3 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0]">Layers</h2>
      <div className="grid gap-2.5">
        {labels.map(([key, label]) => (
          <label key={key} className="flex items-center gap-2.5 text-[var(--body-2)] cursor-pointer">
            <input type="checkbox" className="accent-[var(--accent)] w-4 h-4" checked={layers[key]} onChange={() => onToggle(key)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </section>
  );
}
