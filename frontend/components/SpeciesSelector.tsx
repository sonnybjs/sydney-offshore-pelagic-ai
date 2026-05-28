import type { SpeciesProfile } from "../lib/types";

export function SpeciesSelector({ species, selected, onSelect }: { species: SpeciesProfile[]; selected: string; onSelect: (id: string) => void }) {
  return (
    <section className="panel">
      <h2>Species</h2>
      <div className="speciesGrid">
        {species.map((item) => (
          <button className={item.species_id === selected ? "speciesButton selected" : "speciesButton"} key={item.species_id} onClick={() => onSelect(item.species_id)}>
            {item.common_name.replace(" / Dolphinfish", "")}
          </button>
        ))}
      </div>
    </section>
  );
}
