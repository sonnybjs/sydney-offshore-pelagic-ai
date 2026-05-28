import type { HotspotProperties } from "../lib/types";

export function HotspotCard({ hotspot, selected, onSelect }: { hotspot: HotspotProperties; selected: boolean; onSelect: () => void }) {
  return (
    <button className={selected ? "hotspotCard active" : "hotspotCard"} onClick={onSelect}>
      <div className="cardTop">
        <span className={`rating ${hotspot.rating.toLowerCase()}`}>{hotspot.rating}</span>
        <strong>{hotspot.score}/100</strong>
      </div>
      <h3>{hotspot.area_name}</h3>
      <p className="speciesName">{hotspot.species_name}</p>
      <div className="driverList">
        {hotspot.key_drivers.slice(0, 3).map((driver) => <span key={driver}>{driver}</span>)}
      </div>
      <ul>
        {hotspot.explanation.slice(0, 3).map((line) => <li key={line}>{line}</li>)}
      </ul>
      <p className="strategy">{hotspot.suggested_strategy}</p>
      <p className="finePrint">{hotspot.confidence} confidence. {hotspot.caution_notes[0]}</p>
    </button>
  );
}
