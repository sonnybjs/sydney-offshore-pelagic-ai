"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Header } from "../components/Header";
import { MobileNav } from "../components/MobileNav";
import { PredictionDatePanel } from "../components/PredictionDatePanel";
import { PredictionDisclaimer } from "../components/PredictionDisclaimer";
import { PredictionHotspotList } from "../components/PredictionHotspotList";
import { PredictionMapView } from "../components/PredictionMapView";
import { PredictionModeToggle } from "../components/PredictionModeToggle";
import { ModelSourceToggle } from "../components/ModelSourceToggle";
import { fetchPois, fetchPredictionManifest, fetchPredictionMap, fetchPredictionSpots } from "../lib/api";
import { fallbackPois } from "../lib/mockFallback";
import type { LayerState, ModelSource, POI, PredictionManifest, PredictionMapResponse, PredictionMode } from "../lib/types";

const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");

const speciesOptions = [
  { id: "mahi_mahi", label: "Mahi Mahi" },
  { id: "southern_bluefin_tuna", label: "Southern Bluefin Tuna" },
  { id: "yellowtail_kingfish", label: "Yellowtail Kingfish" },
];

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export default function Home() {
  const [theme, setTheme] = useState("dark");
  const [mode, setMode] = useState<PredictionMode>("demo");
  const [modelSource, setModelSource] = useState<ModelSource>("scikit_learn");
  const [selectedSpecies, setSelectedSpecies] = useState("mahi_mahi");
  const [speciesQuery, setSpeciesQuery] = useState("");
  const [mobileTab, setMobileTab] = useState("map");
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
  const requestSeq = useRef(0);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

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

  const currentDateOptions = useMemo(() => {
    const entry = manifest?.current?.species?.[selectedSpecies];
    return (entry?.available_dates || manifest?.current?.available_dates || [entry?.prediction_date]).filter(Boolean) as string[];
  }, [manifest, selectedSpecies]);

  useEffect(() => {
    if (!dateOptions.length) { setSelectedDate(null); return; }
    if (!selectedDate || !dateOptions.includes(selectedDate)) setSelectedDate(dateOptions[dateOptions.length - 1]);
  }, [dateOptions, selectedDate]);

  useEffect(() => {
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    setSelectedIndex(null);
    setSelectedSpotIndex(null);
    setPrediction(null);
    setSpots(null);
    setMessage(`Loading ${modelSource === "deep_learning" ? "deep learning" : "scikit-learn"} prediction...`);
    const entry = manifest?.[mode]?.species?.[selectedSpecies];
    if (entry && !entry.available) {
      setMessage(entry.reason || "Prediction unavailable for this species.");
      return;
    }
    Promise.all([
      fetchPredictionMap(mode, selectedSpecies, selectedDate, modelSource),
      fetchPredictionSpots(mode, selectedSpecies, 500, selectedDate, modelSource),
    ]).then(([result, spotResult]) => {
      if (requestSeq.current !== seq) return;
      setOffline((c) => c || result.offline);
      if (!result.data) {
        setMessage(mode === "current" ? "Current prediction missing. Run python pipelines/run_generate_demo_and_current_predictions.py" : "Demo prediction missing.");
        return;
      }
      setPrediction(result.data);
      setSpots(spotResult.data);
      setMessage("");
    });
  }, [mode, selectedSpecies, selectedDate, modelSource, manifest]);

  const selectedEntry = manifest?.[mode]?.species?.[selectedSpecies];

  const dateNote = useMemo(() => {
    if (mode === "demo") return "Historical demo date from real feature grids.";
    if (!selectedDate) return "Select a target date.";
    const days = Math.round((new Date(selectedDate).getTime() - Date.now()) / 86400000);
    if (days < 0) return "Past date — showing last trained output, not a forecast.";
    if (days <= 3) return `Forecast horizon +${days} day${days === 1 ? "" : "s"} · model confidence usable.`;
    if (days <= 7) return `+${days} days out · near the horizon edge, confidence degrades.`;
    return `+${days} days is beyond the 7-day forecast horizon.`;
  }, [mode, selectedDate]);

  const filteredSpecies = useMemo(() => {
    const q = speciesQuery.trim().toLowerCase();
    return q ? speciesOptions.filter((s) => s.label.toLowerCase().includes(q)) : speciesOptions;
  }, [speciesQuery]);

  return (
    <main className="min-h-screen p-[18px] max-[860px]:pb-[78px]">
      <Header offline={offline} theme={theme} onTheme={setTheme} />
      <PredictionDisclaimer />

      <div className="dashboard grid [grid-template-columns:300px_minmax(520px,1fr)_360px] gap-4 mt-4 max-[1180px]:[grid-template-columns:280px_1fr]" data-mtab={mobileTab}>

        {/* Left rail */}
        <aside className={cn("left-rail flex flex-col gap-4 min-w-0", mobileTab !== "setup" && "max-[860px]:!hidden")}>

          {/* Prediction Mode */}
          <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
            <h2 className="m-0 mb-3 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0]">Prediction Mode</h2>
            <PredictionModeToggle
              mode={mode} onMode={setMode} selectedDate={selectedDate}
              todayDate={currentDateOptions[0] || null}
              tomorrowDate={currentDateOptions[currentDateOptions.length - 1] || null}
              onToday={() => { setMode("current"); if (currentDateOptions[0]) setSelectedDate(currentDateOptions[0]); }}
              onTomorrow={() => { setMode("current"); if (currentDateOptions.length) setSelectedDate(currentDateOptions[currentDateOptions.length - 1]); }}
            />
            {selectedDate && (
              <div className="flex items-center justify-between gap-2.5 mt-3">
                <label htmlFor="predDate" className="text-[var(--muted)] text-[13px]">Target date</label>
                <input id="predDate" type="date" className="dateInp border border-[var(--line)] bg-[var(--btn-bg)] text-[var(--text)] rounded-btn px-2.5 py-2 font-mono text-[13px] focus:outline-none focus:border-[var(--accent)]"
                  value={selectedDate} min={dateOptions[0]} max={dateOptions[dateOptions.length - 1]}
                  onChange={(e) => e.target.value && setSelectedDate(e.target.value)}
                />
              </div>
            )}
            <p className="mt-2.5 text-[var(--muted)] text-xs">{dateNote}</p>
          </section>

          {/* Model Source */}
          <ModelSourceToggle modelSource={modelSource} onModelSource={setModelSource} />

          {/* Species */}
          <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
            <div className="flex items-center justify-between gap-2.5 mb-3">
              <h2 className="m-0 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0] whitespace-nowrap">Species</h2>
              <span className="text-[11px] text-[var(--muted)] border border-[var(--line)] rounded-full px-2 py-0.5 font-mono">{filteredSpecies.length}/{speciesOptions.length}</span>
            </div>
            <div className="search-wrap relative flex items-center mb-2.5">
              <span className="absolute left-2.5 text-[var(--muted)] flex pointer-events-none"><SearchIcon /></span>
              <input type="search" value={speciesQuery} placeholder="Search species…"
                className="w-full py-[9px] pl-[30px] pr-7 border border-[var(--line)] rounded-btn bg-[var(--btn-bg)] text-[var(--text)] text-[13px] outline-none appearance-none placeholder:text-[var(--muted)] focus:border-[var(--accent)]"
                onChange={(e) => setSpeciesQuery(e.target.value)}
              />
              {speciesQuery && (
                <button className="absolute right-1.5 border-0 bg-transparent text-[var(--muted)] text-[18px] leading-none cursor-pointer px-1.5 py-0.5 rounded-[5px] hover:text-[var(--text)]" onClick={() => setSpeciesQuery("")} aria-label="Clear">&times;</button>
              )}
            </div>
            <div className="grid gap-2">
              {filteredSpecies.map((item) => {
                const entry = manifest?.[mode]?.species?.[item.id];
                return (
                  <button key={item.id}
                    className={cn("w-full text-left border rounded-btn px-3 py-2.5 cursor-pointer text-[var(--text)] text-[15px] transition-colors",
                      selectedSpecies === item.id ? "border-[var(--accent)] bg-[var(--btn-selected)]" : "border-[var(--line)] bg-[var(--btn-bg)]"
                    )}
                    onClick={() => setSelectedSpecies(item.id)}>
                    {item.label}
                    <small className="block mt-1 text-[var(--muted)] text-xs">{entry?.available ? "Available" : "Unavailable"}</small>
                  </button>
                );
              })}
              {filteredSpecies.length === 0 && <p className="text-[var(--muted)] text-[13px] mx-0.5 my-1">No species match &ldquo;{speciesQuery}&rdquo;.</p>}
            </div>
          </section>

          {/* Demo date slider */}
          {dateOptions.length > 1 && (
            <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
              <h2 className="m-0 mb-3 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0]">Demo Date</h2>
              <div className="grid gap-2">
                <input type="range" className="w-full accent-[var(--accent)]"
                  min={0} max={dateOptions.length - 1}
                  value={Math.max(0, dateOptions.indexOf(selectedDate || dateOptions[dateOptions.length - 1]))}
                  onChange={(e) => setSelectedDate(dateOptions[Number(e.target.value)])}
                />
                <strong className="text-[var(--text)] text-[14px]">{selectedDate || dateOptions[dateOptions.length - 1]}</strong>
                <small className="text-[var(--muted)] text-xs">10 available demo dates from real feature grids.</small>
              </div>
            </section>
          )}

          {/* Prediction Status */}
          <PredictionDatePanel mode={mode} speciesId={selectedSpecies} manifest={manifest} prediction={prediction} />
        </aside>

        {/* Center — map */}
        <section className={cn("center-stack flex flex-col gap-4 min-w-0", mobileTab !== "map" && "max-[860px]:!hidden")}>
          {message && (
            <div className="border border-[rgba(248,211,107,0.42)] bg-[rgba(248,211,107,0.1)] text-[#ffe5a1] rounded-btn px-3 py-2.5 text-[13px]">
              {message}
            </div>
          )}
          {selectedEntry?.available === false && (
            <div className="border border-[rgba(248,211,107,0.42)] bg-[rgba(248,211,107,0.1)] text-[#ffe5a1] rounded-btn px-3 py-2.5 text-[13px]">
              {selectedEntry.reason}
            </div>
          )}
          <PredictionMapView
            key={`${mode}-${modelSource}-${selectedSpecies}-${selectedDate || "latest"}`}
            geojson={prediction?.geojson || null}
            spots={spots?.geojson || null}
            pois={pois} layers={layers}
            onLayerToggle={(key) => setLayers((s) => ({ ...s, [key]: !s[key] }))}
            selectedIndex={selectedIndex} selectedSpotIndex={selectedSpotIndex}
            onSelect={setSelectedIndex} onSpotSelect={setSelectedSpotIndex}
          />
        </section>

        {/* Right rail */}
        <aside className={cn("right-rail flex flex-col gap-4 min-w-0", mobileTab !== "spots" && "max-[860px]:!hidden")}>
          <PredictionHotspotList
            geojson={spots?.geojson || null}
            selectedIndex={selectedSpotIndex}
            onSelect={(i) => { setSelectedSpotIndex(i); setMobileTab("map"); }}
          />
          <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
            <h2 className="m-0 mb-3 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0]">Model Notes</h2>
            <p className="text-[var(--body-1)] leading-[1.45]">{prediction?.metadata.notes || selectedEntry?.notes || "Select an available species to load prediction metadata."}</p>
            <p className="mt-2.5 text-[var(--muted)] text-xs">No exact fish-location or guaranteed catch claim is made.</p>
          </section>
        </aside>
      </div>

      <MobileNav tab={mobileTab} onTab={setMobileTab} />
    </main>
  );
}
