import { Search, ResetX } from "../icons.jsx";

export default function Toolbar({
  query,
  onQuery,
  field,
  onField,
  level,
  onLevel,
  fieldOptions = [],
  resetActive,
  onReset,
  countText,
}) {
  return (
    <div className="toolbar">
      <div className="ctl search-box">
        <label htmlFor="q">Search programs</label>
        <div className="search-input-wrap">
          <Search />
          <input
            id="q"
            type="search"
            placeholder="Program, university, or country"
            autoComplete="off"
            aria-describedby="countLive"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="ctl">
        <label htmlFor="fieldSel">Field</label>
        <select id="fieldSel" value={field} onChange={(e) => onField(e.target.value)}>
          <option value="all">All fields</option>
          {fieldOptions.map((o) => (
            <option value={o.code} key={o.code}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div className="ctl">
        <label htmlFor="levelSel">Level</label>
        <select id="levelSel" value={level} onChange={(e) => onLevel(e.target.value)}>
          <option value="all">All levels</option>
          <option value="Bachelor">Bachelor</option>
          <option value="Master">Master</option>
        </select>
      </div>

      <button className={"reset-btn" + (resetActive ? "" : " hidden")} id="resetBtn" data-clear onClick={onReset}>
        <ResetX />
        Reset filters
      </button>

      <p className="results-count" id="countLive" aria-live="polite">
        {countText}
      </p>
    </div>
  );
}
