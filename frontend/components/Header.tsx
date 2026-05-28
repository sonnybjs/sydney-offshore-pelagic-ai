export function Header({ offline }: { offline: boolean }) {
  return (
    <header className="header">
      <div>
        <h1>Sydney Offshore Pelagic AI Map</h1>
        <p>Offshore tuna, marlin and pelagic hotspot suitability demo</p>
      </div>
      <div className={offline ? "status offline" : "status"}>
        {offline ? "Backend offline: fallback mock data" : "Local backend connected"}
      </div>
    </header>
  );
}
