export function DataFreshnessPanel() {
  return (
    <section className="panel">
      <h2>Data Freshness</h2>
      <p>The map uses a real OpenStreetMap base layer. Hotspots and ocean overlays are still mock/demo layers. Initial NSW DPI FAD rows and NASA/GEBCO/AODN source metadata have been saved for future training work.</p>
      <p className="finePrint">Confidence is intentionally limited until observed ocean data and validation datasets are integrated.</p>
    </section>
  );
}
