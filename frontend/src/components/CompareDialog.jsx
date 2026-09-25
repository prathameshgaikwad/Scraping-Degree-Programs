import { TIER } from "../lib/constants.js";
import { Star, Close, Check } from "../icons.jsx";

export default function CompareDialog({ open, list, bestId, topPick, onPick, onClose, compareRef }) {
  const shown = list.slice(0, 6);

  const rows = [
    { label: "Level", html: (p) => p.level },
    { label: "Field", html: (p) => p.field },
    { label: "Country", html: (p) => p.city + ", " + p.country },
    { label: "Duration", html: (p) => p.dur },
    { label: "Mode", html: (p) => p.mode },
    { label: "Intake", html: (p) => p.intake },
    { label: "Grades required", html: (p) => p.grades },
    {
      label: "English",
      html: (p) => {
        const parts = [];
        if (p.ielts != null) parts.push("IELTS " + p.ielts.toFixed(1));
        if (p.toefl != null) parts.push("TOEFL " + p.toefl);
        return parts.length ? parts.join(" · ") : p.englishRequired ? "Required (score n/a)" : "Not required";
      },
    },
    { label: "Fees", html: (p) => <span className="od-nowrap">{p.fee}</span> },
    {
      label: "Match",
      html: (p) => (
        <span className="match-pill od-nowrap">
          {p.match}
          <span className="p-unit">%</span>
        </span>
      ),
    },
    {
      label: "Why it fits",
      html: (p) => (
        <div className="c-focus">
          {p.focus.map((f) => (
            <span className="focus-chip" key={f}>
              <Check />
              {f}
            </span>
          ))}
        </div>
      ),
    },
  ];

  return (
    <div
      className={"compare" + (open ? " open" : "")}
      id="compare"
      role="dialog"
      aria-modal="true"
      aria-labelledby="compareTitle"
      ref={compareRef}
    >
      <div className="compare-head">
        <div>
          <div className="compare-eyebrow">Side by side</div>
          <h3 className="sheet-title" id="compareTitle">
            Compare your shortlist
          </h3>
        </div>
        <button type="button" className="icon-btn" id="compareClose" aria-label="Close compare view" onClick={() => onClose(true)}>
          <Close />
        </button>
      </div>

      <div className="compare-body" id="compareBody">
        {open && (
          <table className="compare-table">
            <thead>
              <tr>
                <th scope="col" className="c-corner">
                  <span className="visually-hidden">Attribute</span>
                </th>
                {shown.map((p) => {
                  const t = TIER[p.tier];
                  const best = bestId === p.id;
                  const pick = topPick === p.id;
                  return (
                    <th scope="col" className={"c-col" + (best ? " is-best" : "")} key={p.id}>
                      <div className="c-name">{p.name}</div>
                      <div className="c-uni">{p.uni}</div>
                      <div className="c-tags">
                        <span className={"chip " + t.cls}>{t.label}</span>
                        {best && <span className="best-pill">Best match</span>}
                      </div>
                      <button
                        type="button"
                        className="pick-btn od-touch"
                        data-pick={p.id}
                        aria-pressed={pick ? "true" : "false"}
                        onClick={() => onPick(p.id)}
                      >
                        <Star />
                        <span>Top pick</span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label}>
                  <th scope="row" className="c-label">
                    {r.label}
                  </th>
                  {shown.map((p) => (
                    <td className={r.label === "Match" && p.id === bestId ? "is-best-td" : ""} key={p.id}>
                      {r.html(p)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="compare-note" id="compareNote">
        {list.length > shown.length
          ? "Showing the 6 highest-match programs — remove some from your shortlist to compare fewer."
          : "Mark a top pick with the star — it also appears next to that program in the list."}
      </p>
      <div className="compare-foot">
        <button type="button" className="btn btn-secondary" id="compareClose2" onClick={() => onClose(true)}>
          Close
        </button>
      </div>
    </div>
  );
}
