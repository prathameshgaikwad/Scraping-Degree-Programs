// Shared constants and helpers, ported from the artifact's inline script.
// The program list itself now comes from the backend (see lib/backend.js).

export const TIER = {
  reach: { label: "Reach", cls: "chip-reach", hint: "Ambitious — a stretch from your profile" },
  target: { label: "Target", cls: "chip-target", hint: "Strong, well-matched program" },
  safety: { label: "Safety", cls: "chip-safety", hint: "Eligible — likely to be a fit" },
};

export const FIELD_ORDER = {
  ARTIFICIAL_INTELLIGENCE: 0,
  MACHINE_LEARNING: 1,
  DATA_SCIENCE: 2,
  DATA_ANALYTICS: 3,
  COMPUTER_SCIENCE: 4,
  ROBOTICS: 5,
  COMPUTER_VISION: 6,
  NLP: 7,
  INTELLIGENT_SYSTEMS: 8,
  AI_ENGINEERING: 9,
  COMPUTATIONAL_SCIENCE: 10,
  UNKNOWN: 11,
};
export const LEVEL_ORDER = { Master: 0, Bachelor: 1 };

export const SORTERS = {
  name: (p) => p.name.toLowerCase(),
  uni: (p) => p.uni.toLowerCase(),
  level: (p) => LEVEL_ORDER[p.level],
  field: (p) => FIELD_ORDER[p.fieldCode] ?? 99,
  country: (p) => (p.country || "").toLowerCase(),
  qsRank: (p) => (p.qsRank == null ? 99999 : p.qsRank),
  feeNum: (p) => p.feeNum,
  match: (p) => p.match,
};

export const COLS = [
  { key: "name", label: "Program", sort: true },
  { key: "level", label: "Level", sort: true },
  { key: "field", label: "Field", sort: true },
  { key: "country", label: "Country", sort: true },
  { key: null, label: "Duration", sort: false },
  { key: "qsRank", label: "QS", sort: true },
  { key: "feeNum", label: "Fees", sort: true },
  { key: "match", label: "Match", sort: true },
  { key: null, label: "", sort: false },
];

export const band = (m) => (m < 70 ? 1 : m < 78 ? 2 : m < 86 ? 3 : m < 92 ? 4 : 5);

export const tierGroups = (list) =>
  ["reach", "target", "safety"].map((t) => ({
    key: t,
    prog: list.filter((p) => p.tier === t),
  }));

export const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
