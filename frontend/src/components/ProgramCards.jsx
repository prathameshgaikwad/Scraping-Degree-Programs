import { Star, Chev, Grad, Globe, Clock } from "../icons.jsx";

export default function ProgramCards({ list, selected, shortSet, topPick, onOpen, onShort }) {
  return (
    <ul className="card-list" id="cardList">
      {list.map((p) => {
        const sel = selected === p.id;
        const on = shortSet.has(p.id);
        const starLabel = (on ? "Remove from shortlist: " : "Add to shortlist: ") + p.name;
        return (
          <li className={"card" + (sel ? " is-selected" : "")} data-id={p.id} key={p.id}>
            <div className="card-top">
              <button type="button" className="card-name" data-open={p.id} onClick={(e) => onOpen(p.id, e)}>
                {topPick === p.id && (
                  <span className="pick-flag" aria-hidden="true">
                    <Star />
                  </span>
                )}
                {p.name} <Chev />
                <span className="card-uni">{p.uni}</span>
              </button>
              <button
                type="button"
                className="star-btn od-touch"
                data-short={p.id}
                aria-pressed={on ? "true" : "false"}
                aria-label={starLabel}
                onClick={(e) => onShort(p.id, "card", e)}
              >
                <Star />
              </button>
            </div>
            <div className="card-meta">
              <span>
                <Grad /> {p.level} · {p.field}
              </span>
              <span>
                <Globe /> {p.country}
              </span>
              <span>
                <Clock /> {p.dur}
              </span>
              <span>
                <Grad /> {p.mode}
              </span>
            </div>
            <div className="card-foot">
              <span className="card-fee od-nowrap">{p.fee}</span>
              <span className="match-pill od-nowrap">
                {p.match}
                <span className="p-unit">%</span> match
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
