import { Star, Chev, SortIcon } from "../icons.jsx";
import { COLS } from "../lib/constants.js";

export default function ProgramTable({
  list,
  selected,
  shortSet,
  topPick,
  sortKey,
  sortDir,
  onSort,
  onOpen,
  onShort,
  onRowClick,
}) {
  return (
    <div className="table-wrap" id="tableWrap">
      <table id="progTable">
        <caption className="visually-hidden">University programs matched to the applicant</caption>
        <thead>
          <tr id="progHead">
            {COLS.map((c, i) => {
              if (!c.sort) {
                if (!c.label)
                  return (
                    <th scope="col" className="th-actions" key={"col-" + i}>
                      <span className="visually-hidden">Actions</span>
                    </th>
                  );
                return (
                  <th scope="col" key={"col-" + i}>
                    {c.label}
                  </th>
                );
              }
              const sortval = sortKey === c.key ? (sortDir === "asc" ? "ascending" : "descending") : "none";
              return (
                <th scope="col" aria-sort={sortval} key={c.key}>
                  <button type="button" className="th-btn" data-sort={c.key} onClick={() => onSort(c.key)}>
                    {c.label} <SortIcon />
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody id="tableBody">
          {list.map((p) => {
            const sel = selected === p.id;
            const on = shortSet.has(p.id);
            const starLabel = (on ? "Remove from shortlist: " : "Add to shortlist: ") + p.name;
            return (
              <tr
                data-id={p.id}
                className={sel ? "is-selected" : ""}
                key={p.id}
                onClick={(e) => {
                  if (e.target.closest("button")) return;
                  onRowClick(p.id, e);
                }}
              >
                <td className="prog-cell">
                  <button type="button" className="prog-name" data-open={p.id} onClick={(e) => onOpen(p.id, e)}>
                    {topPick === p.id && (
                      <span className="pick-flag" aria-hidden="true">
                        <Star />
                      </span>
                    )}
                    {p.name} <Chev />
                  </button>
                  <span className="prog-uni">{p.uni}</span>
                </td>
                <td className="cell-soft">{p.level}</td>
                <td className="cell-soft">{p.field}</td>
                <td className="cell-soft">{p.country}</td>
                <td className="cell-soft">{p.dur}</td>
                <td className="cell-num">{p.qsDisplay ? p.qsDisplay : "—"}</td>
                <td className="cell-fee od-nowrap">{p.fee}</td>
                <td>
                  <span className="match-pill od-nowrap">
                    {p.match}
                    <span className="p-unit">%</span>
                  </span>
                </td>
                <td className="td-actions">
                  <button
                    type="button"
                    className="star-btn"
                    data-short={p.id}
                    aria-pressed={on ? "true" : "false"}
                    aria-label={starLabel}
                    onClick={(e) => onShort(p.id, "table", e)}
                  >
                    <Star />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
