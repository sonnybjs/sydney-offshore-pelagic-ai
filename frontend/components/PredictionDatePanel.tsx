import type { PredictionMapResponse, PredictionManifest, PredictionMode } from "../lib/types";

const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3 py-2 border-b border-[rgba(103,212,255,0.12)] last:border-b-0">
      <span className="text-[var(--muted)] text-[13px]">{label}</span>
      <strong className={cn("text-right text-[13px] text-[var(--text)]", mono && "font-mono")}>{value}</strong>
    </div>
  );
}

export function PredictionDatePanel({ mode, speciesId, manifest, prediction }: {
  mode: PredictionMode;
  speciesId: string;
  manifest: PredictionManifest | null;
  prediction: PredictionMapResponse | null;
}) {
  const entry = manifest?.[mode]?.species?.[speciesId];
  const meta = prediction?.metadata;
  const rows: [string, string, boolean?][] = [
    ["Mode", mode === "demo" ? "DEMO" : "CURRENT / TOMORROW", true],
    ["Model source", meta?.model_source === "deep_learning" ? "Deep Learning" : "Scikit-learn"],
    ["Species", entry?.common_name || speciesId],
    ["Target date", meta?.target_date || entry?.target_date || "Unavailable", true],
    ["Prediction date", meta?.prediction_date || entry?.prediction_date || "Unavailable", true],
    ["SST source", meta?.data_source_dates?.sst || entry?.data_source_dates?.sst || "Unavailable"],
    ["Current source", meta?.data_source_dates?.physics || "Unavailable"],
    ["CHL source", meta?.data_source_dates?.chl || "Unavailable"],
    ["Confidence", meta?.model_confidence || entry?.model_confidence || "Unavailable"],
    ["Audit status", meta?.audit_status || entry?.audit_status || "Unavailable"],
  ];
  return (
    <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
      <h2 className="m-0 mb-3 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0]">Prediction Status</h2>
      <div>
        {rows.map(([k, v, mono]) => <Row key={k} label={k} value={v} mono={mono} />)}
      </div>
      {!entry?.available && (
        <p className="mt-3 border border-[rgba(248,211,107,0.42)] bg-[rgba(248,211,107,0.1)] text-[#ffe5a1] rounded-btn px-3 py-2.5 text-[13px]">
          {entry?.reason || "Prediction unavailable for this species."}
        </p>
      )}
      {meta?.warning && (
        <p className="mt-3 border border-[rgba(248,211,107,0.42)] bg-[rgba(248,211,107,0.1)] text-[#ffe5a1] rounded-btn px-3 py-2.5 text-[13px]">{meta.warning}</p>
      )}
      <p className="mt-2.5 text-[var(--muted)] text-xs">Score type: relative habitat suitability / hotspot score.</p>
    </section>
  );
}
