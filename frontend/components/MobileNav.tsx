const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");
const TABS: [string, string][] = [["setup", "Setup"], ["map", "Map"], ["spots", "Spots"]];

export function MobileNav({ tab, onTab }: { tab: string; onTab: (t: string) => void }) {
  return (
    <nav className="hidden max-[860px]:flex fixed left-0 right-0 bottom-0 z-50 gap-1 p-2 border-t border-[var(--line)] bg-[var(--header-glass)] backdrop-blur-[10px]" aria-label="Mobile navigation">
      {TABS.map(([id, label]) => (
        <button key={id}
          className={cn("flex-1 border rounded-[8px] py-[11px] text-sm font-bold cursor-pointer min-h-[44px]",
            tab === id ? "bg-[var(--btn-selected)] text-[var(--text)] border-[var(--accent)]" : "bg-transparent text-[var(--muted)] border-transparent"
          )}
          onClick={() => onTab(id)}>{label}
        </button>
      ))}
    </nav>
  );
}
