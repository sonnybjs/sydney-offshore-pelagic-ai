import type { PredictionMapResponse, PredictionManifest, PredictionMode } from "../lib/types";

export function PredictionDatePanel({
  mode,
  speciesId,
  manifest,
  prediction
}: {
  mode: PredictionMode;
  speciesId: string;
  manifest: PredictionManifest | null;
  prediction: PredictionMapResponse | null;
}) {
  const entry = manifest?.[mode]?.species?.[speciesId];
  const meta = prediction?.metadata;
  return (
    <section className="panel predictionDatePanel">
      <h2>Prediction Status</h2>
      <div className="metricPanel">
        <div className="metricRow"><span>Mode</span><strong>{mode === "demo" ? "DEMO" : "CURRENT / TOMORROW"}</strong></div>
        <div className="metricRow"><span>Model source</span><strong>{meta?.model_source === "deep_learning" ? "Deep Learning" : "Scikit-learn"}</strong></div>
        <div className="metricRow"><span>Species</span><strong>{entry?.common_name || speciesId}</strong></div>
        <div className="metricRow"><span>Target date</span><strong>{meta?.target_date || entry?.target_date || "Unavailable"}</strong></div>
        <div className="metricRow"><span>Prediction date</span><strong>{meta?.prediction_date || entry?.prediction_date || "Unavailable"}</strong></div>
        <div className="metricRow"><span>SST source</span><strong>{meta?.data_source_dates?.sst || entry?.data_source_dates?.sst || "Unavailable"}</strong></div>
        <div className="metricRow"><span>Current source</span><strong>{meta?.data_source_dates?.physics || "Unavailable"}</strong></div>
        <div className="metricRow"><span>CHL source</span><strong>{meta?.data_source_dates?.chl || "Unavailable"}</strong></div>
        <div className="metricRow"><span>Confidence</span><strong>{meta?.model_confidence || entry?.model_confidence || "Unavailable"}</strong></div>
        <div className="metricRow"><span>Audit status</span><strong>{meta?.audit_status || entry?.audit_status || "Unavailable"}</strong></div>
      </div>
      {!entry?.available && <p className="unavailableText">{entry?.reason || "Prediction unavailable for this species."}</p>}
      {meta?.warning && <p className="unavailableText">{meta.warning}</p>}
      {meta?.score_explanation && <p className="tinyNote">{meta.score_explanation}</p>}
      <p className="tinyNote">Score type: relative habitat suitability / hotspot score.</p>
    </section>
  );
}
