import type { SpeciesProfile } from "../lib/types";

export function SpeciesProfilePanel({ profile }: { profile?: SpeciesProfile }) {
  if (!profile) return null;
  return (
    <section className="panel">
      <h2>Species Profile</h2>
      <h3>{profile.common_name}</h3>
      <div className="metricRow"><span>Preferred SST</span><strong>{profile.preferred_sst_range_c[0]} - {profile.preferred_sst_range_c[1]} C</strong></div>
      <div className="tagList">{profile.ocean_feature_preference.map((item) => <span key={item}>{item}</span>)}</div>
      <p>{profile.seasonality_notes}</p>
      <p className="finePrint">{profile.model_notes}</p>
    </section>
  );
}
