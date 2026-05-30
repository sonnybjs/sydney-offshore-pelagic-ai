export function PredictionDisclaimer() {
  return (
    <section className="mt-4 bg-[var(--panel-glass)] border border-[color-mix(in_srgb,var(--warm)_50%,transparent)] text-[color-mix(in_srgb,var(--warm)_70%,var(--text))] leading-[1.5] rounded-panel p-4 shadow-panel text-[15px]">
      This map displays relative habitat suitability, not exact fish locations or guaranteed catch probability. Always check marine weather, safety requirements, NSW DPI rules, closures, bag limits, and local conditions before any trip.
    </section>
  );
}
