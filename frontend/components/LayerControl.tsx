import type { LayerState } from "../lib/types";

const labels: Array<[keyof LayerState, string]> = [
  ["heatmap", "Habitat heatmap"],
  ["hotspots", "Recommendation points"],
  ["fronts", "SST front proxy"],
  ["currents", "Current arrows"],
  ["pois", "POI markers"],
  ["shelf", "Shelf/depth markers"]
];

export function LayerControl({ layers, onToggle }: { layers: LayerState; onToggle: (key: keyof LayerState) => void }) {
  return (
    <section className="panel">
      <h2>Layers</h2>
      <div className="toggleList">
        {labels.map(([key, label]) => (
          <label key={key} className="toggleRow">
            <input type="checkbox" checked={layers[key]} onChange={() => onToggle(key)} />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </section>
  );
}
