import { useEffect, useRef, useState } from "react";

import { saveProfile } from "../lib/backend.js";
import { Close, Check } from "../icons.jsx";

const DEGREE_LEVELS = ["", "HIGHER_SECONDARY", "DIPLOMA", "BACHELOR", "MASTER", "DOCTORATE", "OTHER"];

function emptyEdu() {
  return { degree: "", field: "", institution: "", country: "", cgpa: "", cgpa_scale: "", percentage: "", graduation_year: "" };
}
function emptyExp() {
  return { title: "", years: "", field: "", domain: "", description: "" };
}
function emptyCourse() {
  return { name: "", credits: "", grade: "" };
}

function toNum(v) {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

// Normalise the backend profile document into editable form state.
function hydrate(profile) {
  const edu = (profile && profile.education) || [];
  const experience = (profile && profile.experience) || [];
  const testing = (profile && profile.testing) || {};
  const coursework = (profile && profile.coursework) || [];
  return {
    name: (profile && profile.name) || "",
    education: edu.length ? edu.map((e) => ({ ...emptyEdu(), ...e })) : [emptyEdu()],
    experience: experience.length ? experience.map((e) => ({ ...emptyExp(), ...e })) : [],
    technical_background: ((profile && profile.technical_background) || []).join(", "),
    target_fields: ((profile && profile.target_fields) || []).join(", "),
    testing: {
      ielts: testing.ielts ?? "",
      toefl: testing.toefl ?? "",
      pte: testing.pte ?? "",
      duolingo: testing.duolingo ?? "",
      gre: testing.gre ?? "",
      gmat: testing.gmat ?? "",
    },
    coursework: coursework.length ? coursework.map((c) => ({ ...emptyCourse(), ...c })) : [],
  };
}

// Build the API payload (only non-empty values).
function serialize(state) {
  const list = (arr, cleaner) => arr.map(cleaner).filter((x) => x && Object.keys(x).length);
  const education = list(state.education, (e) => {
    const out = {};
    if (e.degree) out.degree = e.degree;
    if (e.field) out.field = e.field;
    if (e.institution) out.institution = e.institution;
    if (e.country) out.country = e.country;
    if (toNum(e.cgpa) !== null) out.cgpa = toNum(e.cgpa);
    if (toNum(e.cgpa_scale) !== null) out.cgpa_scale = toNum(e.cgpa_scale);
    if (toNum(e.percentage) !== null) out.percentage = toNum(e.percentage);
    if (toNum(e.graduation_year) !== null) out.graduation_year = toNum(e.graduation_year);
    return out;
  });
  const experience = list(state.experience, (e) => {
    if (!e.title) return null;
    const out = { title: e.title, years: toNum(e.years) ?? 0 };
    if (e.field) out.field = e.field;
    if (e.domain) out.domain = e.domain;
    if (e.description) out.description = e.description;
    return out;
  });
  const coursework = list(state.coursework, (c) => {
    if (!c.name) return null;
    const out = { name: c.name };
    if (toNum(c.credits) !== null) out.credits = toNum(c.credits);
    if (c.grade) out.grade = c.grade;
    return out;
  });
  const testing = {};
  Object.entries(state.testing).forEach(([k, v]) => {
    if (toNum(v) !== null) testing[k] = toNum(v);
  });
  const split = (s) =>
    String(s || "")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  const payload = {
    name: state.name || null,
    education,
    experience,
    coursework,
    technical_background: split(state.technical_background),
    target_fields: split(state.target_fields),
    testing,
  };
  return payload;
}

export default function ProfileEditor({ profile, open, onClose, onSaved, onToast }) {
  const [form, setForm] = useState(() => hydrate(profile));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const panelRef = useRef(null);

  // Re-hydrate whenever the profile is replaced.
  useEffect(() => {
    setForm(hydrate(profile));
    setError("");
  }, [profile]);

  useEffect(() => {
    if (panelRef.current) {
      if (open) panelRef.current.removeAttribute("inert");
      else panelRef.current.setAttribute("inert", "");
    }
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && open) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const setList = (key, index, patch) =>
    setForm((f) => {
      const next = f[key].slice();
      next[index] = { ...next[index], ...patch };
      return { ...f, [key]: next };
    });
  const addRow = (key, row) => setForm((f) => ({ ...f, [key]: [...f[key], row] }));
  const removeRow = (key, index) =>
    setForm((f) => ({ ...f, [key]: f[key].filter((_, i) => i !== index) }));

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const { profile: saved, meta } = await saveProfile(serialize(form));
      onSaved(saved, meta);
      onToast("Profile saved — matches updated");
      onClose();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside
      className={"profile-sheet" + (open ? " open" : "")}
      role="dialog"
      aria-modal="true"
      aria-labelledby="profileTitle"
      ref={panelRef}
    >
      <div className="sheet-head">
        <div>
          <div className="sheet-eyebrow">Applicant profile</div>
          <h3 className="sheet-title" id="profileTitle">
            Your details
          </h3>
        </div>
        <button className="icon-btn" aria-label="Close profile editor" onClick={onClose}>
          <Close />
        </button>
      </div>

      <div className="sheet-body profile-body">
        <div className="upload-row">
          <div className="upload-box upload-disabled">
            <div className="upload-title">
              Resume <span className="upload-soon">coming soon</span>
            </div>
            <p className="upload-hint">Automatic parsing is being improved — enter your details manually below for now.</p>
            <button type="button" className="btn btn-secondary" disabled>
              Upload resume
            </button>
          </div>
          <div className="upload-box upload-disabled">
            <div className="upload-title">
              Transcript <span className="upload-soon">coming soon</span>
            </div>
            <p className="upload-hint">Add coursework and grades manually below so prerequisite matching can run.</p>
            <button type="button" className="btn btn-secondary" disabled>
              Upload transcript
            </button>
          </div>
        </div>

        {error && <p className="profile-error">{error}</p>}

        <h4 className="subtitle">Basics</h4>
        <div className="field-grid">
          <label className="field">
            <span>Name</span>
            <input value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="Your name" />
          </label>
          <label className="field">
            <span>Target fields (comma separated)</span>
            <input
              value={form.target_fields}
              onChange={(e) => set({ target_fields: e.target.value })}
              placeholder="Artificial Intelligence, Data Science"
            />
          </label>
          <label className="field field-wide">
            <span>Skills (comma separated)</span>
            <input
              value={form.technical_background}
              onChange={(e) => set({ technical_background: e.target.value })}
              placeholder="Python, SQL, AWS"
            />
          </label>
        </div>

        <h4 className="subtitle">Education</h4>
        {form.education.map((e, i) => (
          <div className="repeat-card" key={i}>
            <div className="field-grid">
              <label className="field">
                <span>Degree</span>
                <input value={e.degree || ""} onChange={(ev) => setList("education", i, { degree: ev.target.value })} placeholder="B.Tech" />
              </label>
              <label className="field">
                <span>Field</span>
                <input value={e.field || ""} onChange={(ev) => setList("education", i, { field: ev.target.value })} placeholder="Computer Science" />
              </label>
              <label className="field">
                <span>Degree level</span>
                <select value={e.degree_level || ""} onChange={(ev) => setList("education", i, { degree_level: ev.target.value || null })}>
                  {DEGREE_LEVELS.map((l) => (
                    <option value={l} key={l || "auto"}>
                      {l ? l.replace(/_/g, " ") : "Auto-detect"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Institution</span>
                <input value={e.institution || ""} onChange={(ev) => setList("education", i, { institution: ev.target.value })} />
              </label>
              <label className="field">
                <span>Country</span>
                <input value={e.country || ""} onChange={(ev) => setList("education", i, { country: ev.target.value })} />
              </label>
              <label className="field">
                <span>CGPA</span>
                <input value={e.cgpa ?? ""} onChange={(ev) => setList("education", i, { cgpa: ev.target.value })} inputMode="decimal" />
              </label>
              <label className="field">
                <span>CGPA scale</span>
                <input value={e.cgpa_scale ?? ""} onChange={(ev) => setList("education", i, { cgpa_scale: ev.target.value })} inputMode="decimal" placeholder="10" />
              </label>
              <label className="field">
                <span>Percentage</span>
                <input value={e.percentage ?? ""} onChange={(ev) => setList("education", i, { percentage: ev.target.value })} inputMode="decimal" />
              </label>
            </div>
            {form.education.length > 1 && (
              <button type="button" className="row-remove" onClick={() => removeRow("education", i)}>
                Remove
              </button>
            )}
          </div>
        ))}
        <button type="button" className="row-add" onClick={() => addRow("education", emptyEdu())}>
          + Add education
        </button>

        <h4 className="subtitle">Work experience</h4>
        {form.experience.length === 0 && <p className="muted-line">None added.</p>}
        {form.experience.map((x, i) => (
          <div className="repeat-card" key={i}>
            <div className="field-grid">
              <label className="field">
                <span>Title</span>
                <input value={x.title || ""} onChange={(ev) => setList("experience", i, { title: ev.target.value })} placeholder="Software Engineer" />
              </label>
              <label className="field">
                <span>Years</span>
                <input value={x.years ?? ""} onChange={(ev) => setList("experience", i, { years: ev.target.value })} inputMode="decimal" />
              </label>
              <label className="field">
                <span>Field</span>
                <input value={x.field || ""} onChange={(ev) => setList("experience", i, { field: ev.target.value })} />
              </label>
              <label className="field">
                <span>Domain</span>
                <input value={x.domain || ""} onChange={(ev) => setList("experience", i, { domain: ev.target.value })} />
              </label>
            </div>
            <button type="button" className="row-remove" onClick={() => removeRow("experience", i)}>
              Remove
            </button>
          </div>
        ))}
        <button type="button" className="row-add" onClick={() => addRow("experience", emptyExp())}>
          + Add experience
        </button>

        <h4 className="subtitle">Test scores</h4>
        <div className="field-grid">
          {["ielts", "toefl", "pte", "duolingo", "gre", "gmat"].map((k) => (
            <label className="field" key={k}>
              <span>{k.toUpperCase()}</span>
              <input
                value={form.testing[k] ?? ""}
                onChange={(e) => set("testing", { ...form.testing, [k]: e.target.value })}
                inputMode="decimal"
              />
            </label>
          ))}
        </div>

        <h4 className="subtitle">Coursework / prerequisites</h4>
        {form.coursework.length === 0 && (
          <p className="muted-line">Upload a transcript, or add courses manually, to match subject prerequisites.</p>
        )}
        {form.coursework.map((c, i) => (
          <div className="repeat-card" key={i}>
            <div className="field-grid">
              <label className="field field-wide">
                <span>Course</span>
                <input value={c.name || ""} onChange={(ev) => setList("coursework", i, { name: ev.target.value })} placeholder="Linear Algebra" />
              </label>
              <label className="field">
                <span>Credits</span>
                <input value={c.credits ?? ""} onChange={(ev) => setList("coursework", i, { credits: ev.target.value })} inputMode="decimal" />
              </label>
              <label className="field">
                <span>Grade</span>
                <input value={c.grade || ""} onChange={(ev) => setList("coursework", i, { grade: ev.target.value })} />
              </label>
            </div>
            <button type="button" className="row-remove" onClick={() => removeRow("coursework", i)}>
              Remove
            </button>
          </div>
        ))}
        <button type="button" className="row-add" onClick={() => addRow("coursework", emptyCourse())}>
          + Add course
        </button>
      </div>

      <div className="sheet-foot">
        <button type="button" className="btn btn-primary" onClick={handleSave} disabled={saving}>
          <Check />
          {saving ? "Saving…" : "Save profile & re-match"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Cancel
        </button>
      </div>
    </aside>
  );
}
