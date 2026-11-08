// One colour per category, stable across charts and the table. Uncategorized is grey.
const PALETTE = [
  "#6366f1", "#06b6d4", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6", "#ef4444",
  "#14b8a6", "#f97316", "#3b82f6", "#84cc16", "#a855f7", "#0ea5e9", "#eab308",
];

export function categoryColor(categoryId: number | null, name: string | null): string {
  if (categoryId === null || name === "Uncategorized") return "#94a3b8";
  return PALETTE[categoryId % PALETTE.length];
}
