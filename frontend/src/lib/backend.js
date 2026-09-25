// Adapter between the Python backend API (degreeprograms/webapp) and the
// ProgramMatch UI model. Live-only: all data comes from the API.
//
// In dev the Vite proxy forwards /api -> http://127.0.0.1:8000 (see
// vite.config.js). In production the same FastAPI-free server serves this build
// and the API on one origin. VITE_API_BASE is an optional override.

export const API_BASE = (import.meta.env?.VITE_API_BASE || "").replace(/\/+$/, "");

// -- enum labels -------------------------------------------------------------
const FIELD_LABELS = {
  ARTIFICIAL_INTELLIGENCE: "Artificial Intelligence",
  MACHINE_LEARNING: "Machine Learning",
  DATA_SCIENCE: "Data Science",
  DATA_ANALYTICS: "Data Analytics",
  COMPUTER_SCIENCE: "Computer Science",
  ROBOTICS: "Robotics",
  COMPUTER_VISION: "Computer Vision",
  NLP: "Natural Language Processing",
  INTELLIGENT_SYSTEMS: "Intelligent Systems",
  AI_ENGINEERING: "AI Engineering",
  COMPUTATIONAL_SCIENCE: "Computational Science",
  UNKNOWN: "Unclassified",
};

const DEGREE_LABELS = {
  MSC: "MSc",
  MS: "MS",
  MASTER: "Master",
  MA: "MA",
  MENG: "MEng",
  MPHIL: "MPhil",
  MBA: "MBA",
  MRES: "MRes",
  MPHS: "MPhys",
  PGDIP: "PGDip",
  BSC: "BSc",
  BA: "BA",
  BENG: "BEng",
  BACHELOR: "Bachelor",
  UNKNOWN: "Degree n/a",
};

const STATE_LABELS = {
  ELIGIBLE: "Eligible",
  LIKELY_ELIGIBLE: "Likely eligible",
  UNCLEAR: "Unclear",
  PREREQUISITE_GAP: "Prereq gap",
  NOT_ELIGIBLE: "Not eligible",
};

// -- model helpers -----------------------------------------------------------
export const label = (v) => FIELD_LABELS[v] || (v && v !== "UNKNOWN" ? String(v).replace(/_/g, " ") : "Unclassified");
export const degreeLabel = (v) => DEGREE_LABELS[v] || (v && v !== "UNKNOWN" ? String(v) : "Degree n/a");
export const stateLabel = (v) => STATE_LABELS[v] || (v ? String(v).replace(/_/g, " ") : "Not analysed");

export const isMaster = (degreeType) => {
  const m = /^(MSC|MS|MA|MENG|MPHIL|MBA|MRES|MPHYS|MPA|MPP|MPH|PGDIP|MASTER)/;
  return m.test(String(degreeType || "").toUpperCase());
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

// eligibility_state -> the UI's reach / target / safety framing.
function tier(state) {
  if (state === "ELIGIBLE" || state === "LIKELY_ELIGIBLE") return "safety";
  if (state === "NOT_ELIGIBLE" || state === "PREREQUISITE_GAP") return "reach";
  return "target";
}

// QS rank (lower = better) -> a 0-100 "standing" indicator for the blockmap
// colour scale. The backend exposes no fit/probability score by design, so the
// real eligibility state is shown separately.
function matchScore(rank) {
  if (rank == null) return 62;
  return Math.max(62, Math.min(97, 97 - (rank - 1) * 2));
}

const round1 = (v) => (v == null ? null : Math.round(v * 10) / 10);

function requirementsSummary(detail) {
  const req = (detail && detail.requirements) || {};
  const ac = req.academic_requirements || {};
  const lr = req.language_requirements || {};
  const fin = req.financial || {};
  const val = (o) => (o && o.value != null ? o.value : null);

  const grade =
    val(ac.minimum_grade) ||
    (val(ac.minimum_percentage) != null ? val(ac.minimum_percentage) + "%" : null) ||
    (val(ac.minimum_gpa) != null ? "GPA " + val(ac.minimum_gpa) : null) ||
    "Not stated";

  const ielts = val(lr.ielts);
  const toefl = val(lr.toefl);
  const engRequired = lr.english_required && lr.english_required.value;

  return {
    grades: grade,
    ielts: ielts == null ? null : round1(ielts),
    toefl: toefl == null ? null : Math.round(toefl),
    englishRequired: Boolean(engRequired),
    duration: "Duration n/a",
    intake: "See source",
    tuition: val(fin.tuition),
    currency: val(fin.currency) || "",
    period: val(fin.period) || "",
    focus: (req.prerequisites ? req.prerequisites.map((p) => p.requirement || p.category) : []).filter(Boolean).slice(0, 4),
  };
}

function reasonChips(detail) {
  const elig = (detail && detail.eligibility) || null;
  if (!elig) return [];
  const out = [];
  const dims = elig.dimensions || {};
  Object.keys(dims).forEach((k) => {
    const d = dims[k] || {};
    if (d.status === "PASS") out.push(k.replace(/_/g, " "));
  });
  return out.slice(0, 4);
}

export function toProgram(item, detail) {
  const req = requirementsSummary(detail);
  const focus = req.focus.length ? req.focus : [label(item.primary_field)];
  const match = item.eligibility_state ? Math.min(matchScore(item.qs_rank), 96) : matchScore(item.qs_rank);
  return {
    id: item.program_id,
    name: item.name || "Untitled program",
    uni: item.university_name || "Unknown university",
    level: isMaster(item.degree_type) ? "Master" : "Bachelor",
    degreeType: item.degree_type || "UNKNOWN",
    field: label(item.primary_field),
    fieldCode: item.primary_field || "UNKNOWN",
    country: item.country || "—",
    city: item.city || "",
    dur: req.duration,
    grades: req.grades,
    ielts: req.ielts,
    toefl: req.toefl,
    englishRequired: req.englishRequired,
    fee:
      item.tuition_amount != null
        ? `${item.tuition_amount.toLocaleString()} ${item.tuition_currency || ""}`.trim()
        : "Not stated",
    feeNum: item.tuition_amount == null ? Number.POSITIVE_INFINITY : item.tuition_amount,
    intake: req.intake,
    match,
    tier: tier(item.eligibility_state),
    mode:
      item.program_format && item.program_format !== "UNKNOWN"
        ? item.program_format.replace(/_/g, " ").toLowerCase()
        : "—",
    focus,
    qsRank: item.qs_rank,
    qsDisplay: item.qs_rank_display,
    relevance: item.relevance || "UNKNOWN",
    eligibilityState: item.eligibility_state || null,
    eligibilityLabel: stateLabel(item.eligibility_state),
    analysed: Boolean(item.analysed),
    evidenceCount: item.evidence_count || 0,
    reasons: reasonChips(detail),
    _detail: detail || null,
  };
}

// -- loaders -----------------------------------------------------------------
async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

const api = (path) => `${API_BASE}${path}`;

export async function loadBackendData() {
  const [meta, profile, programs] = await Promise.all([
    fetchJson(api("/api/meta")),
    fetchJson(api("/api/profile")),
    fetchJson(api("/api/programs?limit=5000")),
  ]);
  return { meta, profile, programs: programs.results };
}

export async function loadDetail(programId) {
  return fetchJson(api(`/api/programs/${encodeURIComponent(programId)}`));
}

// -- applicant profile (editable) -------------------------------------------
export async function saveProfile(profileDoc) {
  const res = await fetch(api("/api/profile"), {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile: profileDoc }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || body.error || `save failed (${res.status})`);
  return body; // { profile, meta }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(new Error("could not read file"));
    reader.readAsDataURL(file);
  });
}

// NOTE: resume/transcript parsing is abstracted behind the backend's pluggable
// parsing layer and is currently disabled (default provider = null). This helper
// is kept so the UI can re-enable uploads once parsing quality improves.
export async function uploadDocument(file, kind, apply = false) {
  const content = await fileToBase64(file);
  const res = await fetch(api("/api/profile/parse"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, kind, content, apply }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `upload failed (${res.status})`);
  return body;
}

export async function reloadPrograms() {
  const programs = await fetchJson(api("/api/programs?limit=5000"));
  return programs.results;
}
