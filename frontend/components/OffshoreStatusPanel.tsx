import type { OceanCondition } from "../lib/types";

export function OffshoreStatusPanel({ ocean }: { ocean: OceanCondition }) {
  return (
    <section className="panel metricPanel">
      <h2>Mock Ocean Status</h2>
      <div className="metricRow"><span>SST range</span><strong>{ocean.sst_min_c} - {ocean.sst_max_c} C</strong></div>
      <div className="metricRow"><span>Current</span><strong>{ocean.dominant_current_direction}</strong></div>
      <div className="metricRow"><span>Strength</span><strong>{ocean.current_strength_label}</strong></div>
      <div className="metricRow"><span>Chlorophyll</span><strong>{ocean.chlorophyll_status}</strong></div>
      <div className="metricRow"><span>SLA / eddy</span><strong>{ocean.sea_level_anomaly_status}</strong></div>
      <p className="finePrint">{ocean.freshness_note}</p>
    </section>
  );
}
