export function MapLegend() {
  return (
    <div className="absolute left-[14px] bottom-[14px] z-[8] flex flex-wrap gap-2.5 p-2.5 border border-[rgba(255,255,255,0.16)] bg-[var(--overlay-glass)] rounded-[7px] text-[var(--body-2)] text-[12px] pointer-events-none">
      <span className="flex items-center gap-1.5"><i className="inline-block w-[11px] h-[11px] rounded-[3px] scoreLow" /> Low</span>
      <span className="flex items-center gap-1.5"><i className="inline-block w-[11px] h-[11px] rounded-[3px] scorePossible" /> Possible</span>
      <span className="flex items-center gap-1.5"><i className="inline-block w-[11px] h-[11px] rounded-[3px] scoreGood" /> Good</span>
      <span className="flex items-center gap-1.5"><i className="inline-block w-[11px] h-[11px] rounded-[3px] scorePrime" /> Prime</span>
    </div>
  );
}
