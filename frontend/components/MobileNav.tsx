const TABS: [string, string][] = [["setup", "Setup"], ["map", "Map"], ["spots", "Spots"]];

export function MobileNav({ tab, onTab }: { tab: string; onTab: (t: string) => void }) {
  return (
    <nav className="mobileNav" aria-label="Mobile navigation">
      {TABS.map(([id, label]) => (
        <button key={id} className={tab === id ? "active" : ""} onClick={() => onTab(id)}>
          {label}
        </button>
      ))}
    </nav>
  );
}
