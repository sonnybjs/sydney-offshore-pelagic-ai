export function Header({ offline, theme, onTheme }: { offline: boolean; theme: string; onTheme: (t: string) => void }) {
  return (
    <header className="header">
      <div>
        <h1>Sydney Offshore Pelagic AI Map</h1>
        <p>Offshore tuna, marlin and pelagic hotspot suitability demo</p>
      </div>
      <div className="headerRight">
        <div className="themeToggle" role="group" aria-label="Theme">
          <button className={theme === "dark" ? "active" : ""} onClick={() => onTheme("dark")}>Dark</button>
          <button className={theme === "light" ? "active" : ""} onClick={() => onTheme("light")}>Light</button>
        </div>
        <div className={offline ? "status offline" : "status"}>
          {offline ? "Backend offline: fallback mock data" : "Local backend connected"}
        </div>
      </div>
    </header>
  );
}
