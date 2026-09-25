import { TIER } from "../lib/constants.js";
import { Star, Pin, Close, Check } from "../icons.jsx";

export default function DetailSheet({ program, detail, open, shortSet, onShort, onClose, sheetRef, shortBtnRef }) {
  const on = program ? shortSet.has(program.id) : false;
  const tier = program ? TIER[program.tier] : null;

  const englishText = (() => {
    if (!program) return "Not stated";
    if (!program.englishRequired && program.ielts == null && program.toefl == null) return "Not required";
    const parts = [];
    if (program.ielts != null) parts.push("IELTS " + program.ielts.toFixed(1));
    if (program.toefl != null) parts.push("TOEFL " + program.toefl);
    return parts.length ? parts.join(" · ") : "Required";
  })();

  const reasons = (program && program.reasons) || [];
  const focus = (program && program.focus) || [];
  const focusItems = [...new Set([...reasons, ...focus])].slice(0, 6);
  const eligibilityReason =
    detail && detail.eligibility && (detail.eligibility.reasons || [])[0] ? detail.eligibility.reasons[0] : null;

  return (
    <aside
      className={"sheet" + (open ? " open" : "")}
      id="sheet"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sheetTitle"
      ref={sheetRef}
    >
      <div className="sheet-head">
        <div>
          <div className="sheet-eyebrow" id="sheetEyebrow">
            {program ? program.level + " · " + program.field : ""}
          </div>
          <h3 className="sheet-title" id="sheetTitle">
            {program ? program.name : "Program"}
          </h3>
        </div>
        <button className="icon-btn" id="sheetClose" aria-label="Close panel" onClick={() => onClose(true)}>
          <Close />
        </button>
      </div>

      {program && (
        <div className="sheet-body">
          <p className="sheet-uni" id="sheetUni">
            <Pin /> {program.uni + (program.city ? " — " + program.city : "") + (program.country ? ", " + program.country : "")}
          </p>
          <div className="meta-chips" id="sheetMeta">
            <span className="chip">{program.level}</span>
            <span className="chip">{program.field}</span>
            <span className="chip">{program.mode === "—" ? "Format n/a" : program.mode}</span>
            {program.qsDisplay && <span className="chip">QS {program.qsDisplay}</span>}
          </div>

          <div className="match-meter">
            <div>
              <div className="mm-num" id="sheetMatch">
                {program.match}
              </div>
              <div className="mm-cap">standing</div>
            </div>
            <div className="mm-bar">
              <span id="sheetBar" style={{ width: program.match + "%" }} />
            </div>
            <span className={"chip " + tier.cls} id="sheetTier">
              {program.eligibilityState ? program.eligibilityLabel : tier.label}
            </span>
          </div>

          <h4 className="subtitle">Why it matches your profile</h4>
          <div className="focus-list" id="sheetFocus">
            {focusItems.length ? (
              focusItems.map((f) => (
                <span className="focus-chip" key={f}>
                  <Check />
                  {f}
                </span>
              ))
            ) : (
              <span className="focus-chip">Not enough requirement evidence captured</span>
            )}
          </div>

          <h4 className="subtitle">Key requirements</h4>
          <div className="req-grid">
            <div className="req">
              <div className="lbl">Grades</div>
              <div className="val" id="sheetGrades">
                {program.grades}
              </div>
            </div>
            <div className="req">
              <div className="lbl">English</div>
              <div className="val" id="sheetEnglish">
                {englishText}
              </div>
            </div>
            <div className="req">
              <div className="lbl">Fees</div>
              <div className="val" id="sheetFees">
                {program.fee}
              </div>
            </div>
            <div className="req">
              <div className="lbl">Intake</div>
              <div className="val" id="sheetIntake">
                {program.intake}
              </div>
            </div>
            <div className="req">
              <div className="lbl">Duration</div>
              <div className="val" id="sheetDur">
                {program.dur}
              </div>
            </div>
          </div>
          {eligibilityReason && (
            <p className="sheet-note">
              {program.eligibilityLabel}: {eligibilityReason}
            </p>
          )}
          {program.evidenceCount > 0 && (
            <p className="sheet-note">{program.evidenceCount} evidence source(s) captured for this program.</p>
          )}
        </div>
      )}

      <div className="sheet-foot">
        <button
          className="btn btn-primary"
          id="sheetShort"
          ref={shortBtnRef}
          aria-pressed={on ? "true" : "false"}
          onClick={() => onShort(program && program.id, "sheet")}
        >
          <Star size={17} />
          <span id="sheetShortLabel">{on ? "Added — remove from shortlist" : "Add to shortlist"}</span>
        </button>
        <button className="btn btn-secondary" id="sheetClose2" onClick={() => onClose(true)}>
          Close
        </button>
      </div>
    </aside>
  );
}
