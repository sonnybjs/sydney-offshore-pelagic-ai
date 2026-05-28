export function scoreColor(score: number) {
  if (score >= 95) return "#ff4f8b";
  if (score >= 85) return "#ffb84d";
  if (score >= 60) return "#55d6a0";
  return "#2f8bd8";
}

export function scoreOpacity(score: number) {
  return Math.max(0.12, Math.min(0.5, score / 160));
}
