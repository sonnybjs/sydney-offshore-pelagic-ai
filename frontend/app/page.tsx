"use client";

import { useEffect, useMemo, useState } from "react";
import { Header } from "../components/Header";
import { LayerControl } from "../components/LayerControl";
import { PredictionDatePanel } from "../components/PredictionDatePanel";
import { PredictionDisclaimer } from "../components/PredictionDisclaimer";
import { PredictionHotspotList } from "../components/PredictionHotspotList";
import { PredictionMapView } from "../components/PredictionMapView";
import { PredictionModeToggle } from "../components/PredictionModeToggle";
import { fetchPois, fetchPredictionManifest, fetchPredictionMap, fetchPredictionSpots } from "../lib/api";
import { fallbackPois } from "../lib/mockFallback";
import type { LayerState, POI, PredictionManifest, PredictionMapResponse, PredictionMode } from "../lib/types";

const speciesOptions = [
  { id: "mahi_mahi", label: "Mahi Mahi" },
  { id: "southern_bluefin_tuna", label: "Southern Bluefin Tuna" },
  { id: "yellowtail_kingfish", label: "Yellowtail Kingfish" }
];

export default function Home() {
  const [mode, setMode] = useState<PredictionMode>("demo");
  const [selectedSpecies, setSelectedSpecies] = useState("mahi_mahi");
  const [manifest, setManifest] = useState<PredictionManifest | null>(null);
  const [prediction, setPrediction] = useState<PredictionMapResponse | null>(null);
  const [spots, setSpots] = useState<PredictionMapResponse | null>(null);
  const [pois, setPois] = useState<POI[]>(fallbackPois);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [selectedSpotIndex, setSelectedSpotIndex] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [layers, setLayers] = useState<LayerState>({ heatmap: true, hotspots: true, sst: false, fronts: false, currents: false, pois: true, shelf: true });

  useEffect(() => {
    Promise.all([fetchPredictionManifest(), fetchPois()]).then(([manifestResult, poiResult]) => {
      setManifest(manifestResult.data);
      setPois(poiResult.data);
      setOffline(manifestResult.offline || poiResult.offline);
      const demoSpecies = manifestResult.data.demo?.species || {};
      const preferred = demoSpecies.mahi_mahi?.available ? "mahi_mahi" : demoSpecies.southern_bluefin_tuna?.available ? "southern_bluefin_tuna" : "yellowtail_kingfish";
      setSelectedSpecies(preferred);
      setSelectedDate((demoSpecies[preferred]?.available_dates || [demoSpecies[preferred]?.prediction_date]).filter(Boolean).at(-1) || null);
    });
  }, []);

  const dateOptions = useMemo(() => {
    const entry = manifest?.[mode]?.species?.[selectedSpecies];
    return (entry?.available_dates || [entry?.prediction_date]).filter(Boolean) as string[];
  }, [manifest, mode, selectedSpecies]);

  useEffect(() => {
    if (!dateOptions.length) {
      setSelectedDate(null);
      return;
    }
    if (!selectedDate || !dateOptions.includes(selectedDate)) setSelectedDate(dateOptions[dateOptions.length - 1]);
  }, [dateOptions, selectedDate]);

  useEffect(() => {
    setSelectedIndex(null);
    setSelectedSpotIndex(null);
    setMessage("");
    const entry = manifest?.[mode]?.species?.[selectedSpecies];
    if (entry && !entry.available) {
      setPrediction(null);
      setSpots(null);
      setMessage(entry.reason || "Prediction unavailable for this species.");
      return;
    }
    Promise.all([fetchPredictionMap(mode, selectedSpecies, selectedDate), fetchPredictionSpots(mode, selectedSpecies, 500, selectedDate)]).then(([result, spotResult]) => {
      setOffline((current) => current || result.offline);
      if (!result.data) {
        setPrediction(null);
        setSpots(null);
        setMessage(mode === "current" ? "Current prediction missing. Run python pipelines/run_generate_demo_and_current_predictions.py" : "Demo prediction missing.");
        return;
      }
      setPrediction(result.data);
      setSpots(spotResult.data);
    });
  }, [mode, selectedSpecies, selectedDate, manifest]);

  const selectedEntry = manifest?.[mode]?.species?.[selectedSpecies];
  const subtitle = useMemo(() => {
    if (mode === "current") return "Tomorrow target: 2026-05-28";
    return "Historical trained-model prediction demo";
  }, [mode]);

  return (
    <main>
      <Header offline={offline} />
      <div className="predictionDashboard">
        <aside className="leftRail">
          <section className="panel">
            <h2>Prediction Mode</h2>
            <PredictionModeToggle mode={mode} onMode={setMode} />
            <p className="tinyNote">{subtitle}</p>
          </section>
          <section className="panel">
            <h2>Species</h2>
            <div className="speciesGrid">
              {speciesOptions.map((item) => {
                const entry = manifest?.[mode]?.species?.[item.id];
                return (
                  <button key={item.id} className={selectedSpecies === item.id ? "speciesButton selected" : "speciesButton"} onClick={() => setSelectedSpecies(item.id)}>
                    {item.label}
                    <small>{entry?.available ? "Available" : "Unavailable"}</small>
                  </button>
                );
              })}
            </div>
          </section>
          <LayerControl layers={layers} onToggle={(key) => setLayers((state) => ({ ...state, [key]: !state[key] }))} />
          {dateOptions.length > 1 && (
            <section className="panel">
              <h2>Demo Date</h2>
              <div className="dateSliderPanel">
                <input
                  type="range"
                  min={0}
                  max={dateOptions.length - 1}
                  value={Math.max(0, dateOptions.indexOf(selectedDate || dateOptions[dateOptions.length - 1]))}
                  onChange={(event) => setSelectedDate(dateOptions[Number(event.target.value)])}
                />
                <strong>{selectedDate || dateOptions[dateOptions.length - 1]}</strong>
                <small>10 available demo dates from real feature grids.</small>
              </div>
            </section>
          )}
          <PredictionDatePanel mode={mode} speciesId={selectedSpecies} manifest={manifest} prediction={prediction} />
        </aside>
        <section className="centerStack">
          {message && <div className="predictionNotice">{message}</div>}
          {selectedEntry?.available === false && <div className="predictionNotice">{selectedEntry.reason}</div>}
          <PredictionMapView geojson={prediction?.geojson || null} spots={spots?.geojson || null} pois={pois} layers={layers} selectedIndex={selectedIndex} selectedSpotIndex={selectedSpotIndex} onSelect={setSelectedIndex} onSpotSelect={setSelectedSpotIndex} />
          <PredictionDisclaimer />
        </section>
        <aside className="rightRail">
          <PredictionHotspotList geojson={spots?.geojson || null} selectedIndex={selectedSpotIndex} onSelect={setSelectedSpotIndex} />
          <section className="panel">
            <h2>Model Notes</h2>
            <p>{prediction?.metadata.notes || selectedEntry?.notes || "Select an available species to load prediction metadata."}</p>
            <p className="tinyNote">No exact fish-location or guaranteed catch claim is made.</p>
          </section>
        </aside>
      </div>
    </main>
  );
}
