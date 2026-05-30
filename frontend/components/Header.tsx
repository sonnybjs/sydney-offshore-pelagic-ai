const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");

export function Header({ offline, theme, onTheme }: { offline: boolean; theme: string; onTheme: (t: string) => void }) {
  return (
    <header className="header flex justify-between items-center gap-x-[18px] gap-y-3.5 flex-wrap px-[22px] py-[18px] border border-[var(--line)] bg-[var(--header-glass)] rounded-panel backdrop-blur-[6px]">
      <div className="min-w-0 flex flex-col gap-2">
        <h1 className="m-0 text-[clamp(24px,2.6vw,36px)] leading-[1.12] text-[var(--text)] font-bold">{`Sydney Offshore Pelagic AI Map`}</h1>
        <p className="m-0 text-[var(--muted)] text-[15px]">Offshore tuna, marlin and pelagic hotspot suitability demo</p>
      </div>
      <div className="header-right flex items-center gap-3.5">
        <div className="flex gap-1 p-1 border border-[var(--line)] rounded-full bg-[var(--btn-bg)]" role="group" aria-label="Theme">
          <button className={cn("border-0 rounded-full px-[13px] py-1.5 cursor-pointer text-[13px] font-bold", theme === "dark" ? "bg-[var(--accent)] text-[var(--bg)]" : "bg-transparent text-[var(--muted)]")} onClick={() => onTheme("dark")}>Dark</button>
          <button className={cn("border-0 rounded-full px-[13px] py-1.5 cursor-pointer text-[13px] font-bold", theme === "light" ? "bg-[var(--accent)] text-[var(--bg)]" : "bg-transparent text-[var(--muted)]")} onClick={() => onTheme("light")}>Light</button>
        </div>
        <div className={cn("px-3 py-2 border rounded-full text-[13px] whitespace-nowrap", offline ? "text-[var(--warm)] border-[rgba(248,211,107,0.45)]" : "text-[var(--accent)] border-[rgba(103,212,255,0.45)]")}>
          {offline ? "Backend offline: fallback mock data" : "Local backend connected"}
        </div>
      </div>
    </header>
  );
}
