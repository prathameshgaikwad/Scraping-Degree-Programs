import { useState } from "react";

import { TIER, band, tierGroups } from "../lib/constants.js";

const COLLAPSED_LIMIT = 175;

export default function MatchMap({ list, selected, onSelect, onReset }) {
  const empty = list.length === 0;
  const [expanded, setExpanded] = useState({});
  return (
    <section className="panel" aria-labelledby="mapTitle">
      <div className="section-head">
        <h2 id="mapTitle">Most likely programs</h2>
        <p className="hint">Tiles are programs · color = match score · rows = admission likelihood</p>
      </div>
      <div className="legend" role="group" aria-label="Blockmap legend">
        <div className="legend-item legend-scale">
          <span className="lbl">Match score</span>
          <div className="swatches" aria-hidden="true">
            <span className="sw sw1" />
            <span className="sw sw2" />
            <span className="sw sw3" />
            <span className="sw sw4" />
            <span className="sw sw5" />
          </div>
          <div className="scale-nums" aria-hidden="true">
            <span>68</span>
            <span>75</span>
            <span>82</span>
            <span>89</span>
            <span>96</span>
          </div>
        </div>
        <div className="legend-item">
          <span className="chip chip-reach">Reach</span>
          <span>Ambitious</span>
        </div>
        <div className="legend-item">
          <span className="chip chip-target">Target</span>
          <span>Strong match</span>
        </div>
        <div className="legend-item">
          <span className="chip chip-safety">Safety</span>
          <span>Likely fit</span>
        </div>
      </div>

      <div className="hm" id="hm">
        {!empty &&
          tierGroups(list).map((g) => {
            if (!g.prog.length) return null;
            const t = TIER[g.key];
            const isExpanded = Boolean(expanded[g.key]);
            const hasMore = g.prog.length > COLLAPSED_LIMIT;
            const shown = hasMore && !isExpanded ? g.prog.slice(0, COLLAPSED_LIMIT) : g.prog;
            return (
              <div className="hm-group" key={g.key}>
                <div className="hm-tier">
                  <span className={"chip " + t.cls}>{t.label}</span>
                  <span className="hm-tier-hint">{t.hint}</span>
                  <span className="hm-tier-count">
                    {g.prog.length} program{g.prog.length === 1 ? "" : "s"}
                    {hasMore && !isExpanded ? " · showing " + shown.length : ""}
                  </span>
                </div>
                <div className="hm-cells">
                  {shown.map((p) => {
                    const sel = selected === p.id;
                    const lbl =
                      p.name + " at " + p.uni + ", " + p.match + "% match, " + t.label + " tier. Open program details.";
                    return (
                      <button
                        type="button"
                        key={p.id}
                        className={"hm-cell heat-" + band(p.match) + (sel ? " is-selected" : "")}
                        data-cell={p.id}
                        aria-pressed={sel ? "true" : "false"}
                        aria-label={lbl}
                        onClick={() => onSelect(p.id)}
                      >
                        <span className="hm-tip" role="tooltip">
                          <b>{p.uni}</b>
                          <span className="tier">
                            {t.label} · {p.match}% match
                          </span>
                          <span>{p.name}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
                {hasMore && (
                  <button
                    type="button"
                    className="hm-more"
                    aria-expanded={isExpanded ? "true" : "false"}
                    onClick={() => setExpanded((prev) => ({ ...prev, [g.key]: !prev[g.key] }))}
                  >
                    {isExpanded ? (
                      <>
                        Show less <span className="caret">▴</span>
                      </>
                    ) : (
                      <>
                        Show all {g.prog.length} <span className="caret">▾</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            );
          })}
      </div>

      {empty && (
        <div className="empty show" id="mapEmpty">
          <h3>No programs match those filters</h3>
          <p>Try a broader search, or clear the filters to see the full list.</p>
          <button className="btn btn-secondary" data-clear onClick={onReset}>
            Reset filters
          </button>
        </div>
      )}

      <p className="map-foot">Tap a tile to inspect that program. Darker tiles mean a stronger fit for your profile.</p>
    </section>
  );
}
