import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SORTERS } from "./lib/constants.js";
import { loadBackendData, loadDetail, toProgram, reloadPrograms } from "./lib/backend.js";

import Header from "./components/Header.jsx";
import Hero from "./components/Hero.jsx";
import MatchMap from "./components/MatchMap.jsx";
import Toolbar from "./components/Toolbar.jsx";
import ProgramTable from "./components/ProgramTable.jsx";
import ProgramCards from "./components/ProgramCards.jsx";
import DetailSheet from "./components/DetailSheet.jsx";
import CompareDialog from "./components/CompareDialog.jsx";
import ProfileEditor from "./components/ProfileEditor.jsx";
import Toast from "./components/Toast.jsx";

export default function App() {
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [error, setError] = useState("");
  const [meta, setMeta] = useState(null);
  const [profile, setProfile] = useState(null);
  const [programs, setPrograms] = useState([]);
  const detailsRef = useRef({});
  const detailCacheRef = useRef({});

  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  const [field, setField] = useState("all");
  const [level, setLevel] = useState("all");
  const [sortKey, setSortKey] = useState("match");
  const [sortDir, setSortDir] = useState("desc");
  const [short, setShort] = useState(() => new Set());
  const [showShort, setShowShort] = useState(false);
  const [selected, setSelected] = useState(null);
  const [topPick, setTopPick] = useState(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [activeDetail, setActiveDetail] = useState(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [toast, setToast] = useState({ show: false, msg: "" });

  const sheetRef = useRef(null);
  const compareRef = useRef(null);
  const sheetShortRef = useRef(null);
  const compareBtnRef = useRef(null);
  const lastFocusRef = useRef(null);
  const pendingFocusRef = useRef(null);
  const toastTimer = useRef(null);

  // -- load backend data -----------------------------------------------------
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await loadBackendData();
        if (!alive) return;
        detailsRef.current = {};
        setMeta(data.meta);
        setProfile(data.profile);
        setPrograms(data.programs.map((item) => toProgram(item, null)));
        setStatus("ready");
      } catch (err) {
        if (!alive) return;
        setError(err.message || String(err));
        setStatus("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const total = programs.length;

  const fieldOptions = useMemo(() => {
    const seen = new Map();
    programs.forEach((p) => {
      if (!p.fieldCode || p.fieldCode === "UNKNOWN") return;
      seen.set(p.fieldCode, p.field);
    });
    return [...seen.entries()].map(([code, label]) => ({ code, label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [programs]);

  // Debounced search (120ms), matching the artifact's behaviour.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(query);
      setSelected(null);
    }, 120);
    return () => clearTimeout(t);
  }, [query]);

  const list = useMemo(() => {
    let out = showShort ? programs.filter((p) => short.has(p.id)) : programs.slice();

    const term = q.trim().toLowerCase();
    if (term) {
      const tokens = term.split(/\s+/);
      out = out.filter((p) => {
        const hay = (p.name + " " + p.uni + " " + p.field + " " + p.country + " " + p.city + " " + p.level + " " + p.tier).toLowerCase();
        return tokens.every((t) => hay.indexOf(t) !== -1);
      });
    }
    if (field !== "all") out = out.filter((p) => p.fieldCode === field);
    if (level !== "all") out = out.filter((p) => p.level === level);

    const getter = SORTERS[sortKey] || SORTERS.match;
    out.sort((a, b) => {
      const va = getter(a);
      const vb = getter(b);
      const r = va < vb ? -1 : va > vb ? 1 : 0;
      if (r === 0) return a.name.localeCompare(b.name);
      return sortDir === "asc" ? r : -r;
    });
    return out;
  }, [programs, q, field, level, showShort, short, sortKey, sortDir]);

  const count = list.length;
  const avg = count ? Math.round(list.reduce((s, p) => s + p.match, 0) / count) : 0;
  const shortCount = short.size;
  const empty = count === 0;

  const countText = showShort
    ? "Shortlisted · " + count + " program" + (count === 1 ? "" : "s")
    : "Showing " + count + " of " + total + " programs";

  const resetActive = q.trim() !== "" || field !== "all" || level !== "all" || showShort || short.size > 0;

  const shortlistedSorted = useMemo(() => {
    const out = [];
    short.forEach((id) => {
      const p = programs.find((x) => x.id === id);
      if (p) out.push(p);
    });
    out.sort((a, b) => b.match - a.match);
    return out;
  }, [short, programs]);

  const compareBestId = useMemo(() => {
    const shown = shortlistedSorted.slice(0, 6);
    let max = -1;
    let id = null;
    shown.forEach((p) => {
      if (p.match > max) {
        max = p.match;
        id = p.id;
      }
    });
    return id;
  }, [shortlistedSorted]);

  const program = selected ? programs.find((p) => p.id === selected) || null : null;

  const showToast = useCallback((msg) => {
    setToast({ show: true, msg });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast((t) => ({ ...t, show: false })), 2200);
  }, []);

  // Called after the profile is saved or a document applied: refresh matches.
  const handleProfileSaved = useCallback(
    async (savedProfile, meta) => {
      setProfile(savedProfile);
      if (meta) setMeta((prev) => ({ ...prev, ...meta }));
      try {
        const rows = await reloadPrograms();
        setPrograms(rows.map((item) => toProgram(item, null)));
        detailCacheRef.current = {};
      } catch {
        /* keep the current list if the refresh fails */
      }
    },
    []
  );

  const restoreFocus = useCallback(() => {
    const pf = pendingFocusRef.current;
    if (!pf) return;
    pendingFocusRef.current = null;
    let el = null;
    if (pf.from === "sheet") {
      el = sheetShortRef.current;
    } else if (pf.from === "sort") {
      el = document.querySelector('[data-sort="' + pf.key + '"]');
    } else {
      const host = document.getElementById(pf.from === "card" ? "cardList" : "tableWrap");
      if (host) el = host.querySelector('[data-short="' + pf.id + '"]');
    }
    if (el) setTimeout(() => el.focus(), 20);
  }, []);

  useEffect(() => {
    restoreFocus();
  }, [short, sortKey, sortDir, restoreFocus]);

  const toggleShort = useCallback(
    (id, from) => {
      if (!id) return;
      const p = programs.find((x) => x.id === id);
      if (!p) return;
      let on;
      setShort((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
          on = false;
        } else {
          next.add(id);
          on = true;
        }
        return next;
      });
      if (short.has(id)) setTopPick((prev) => (prev === id ? null : prev));
      pendingFocusRef.current = { id, from };
      showToast(on ? "Added " + p.name + " to your shortlist" : "Removed " + p.name + " from your shortlist");
    },
    [short, programs, showToast]
  );

  const openDetail = useCallback(
    async (id, ev) => {
      lastFocusRef.current = ev && ev.currentTarget ? ev.currentTarget : null;
      setSelected(id);
      setSheetOpen(true);
      const local = detailsRef.current[id];
      if (local) {
        setActiveDetail(local);
        return;
      }
      if (detailCacheRef.current[id]) {
        setActiveDetail(detailCacheRef.current[id]);
        return;
      }
      setActiveDetail(null);
      try {
        const detail = await loadDetail(id);
        if (detail) {
          detailCacheRef.current[id] = detail;
          setActiveDetail(detail);
        }
      } catch {
        /* detail view degrades gracefully to summary-only */
      }
    },
    []
  );

  const closeDetail = useCallback((restore) => {
    setSheetOpen(false);
    if (restore && lastFocusRef.current) {
      const el = lastFocusRef.current;
      setTimeout(() => el.focus(), 20);
    }
    lastFocusRef.current = null;
  }, []);


  const openCompare = useCallback(() => {
    if (short.size < 2) return;
    if (sheetOpen) closeDetail(false);
    lastFocusRef.current = compareBtnRef.current;
    setCompareOpen(true);
  }, [short, sheetOpen, closeDetail]);

  const closeCompare = useCallback((restore) => {
    setCompareOpen(false);
    if (restore && lastFocusRef.current) {
      const el = lastFocusRef.current;
      setTimeout(() => el.focus(), 20);
    }
    lastFocusRef.current = null;
  }, []);

  const onSort = useCallback((key) => {
    setSortKey((prevKey) => {
      if (prevKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return prevKey;
      }
      setSortDir("asc");
      return key;
    });
    pendingFocusRef.current = { from: "sort", key };
  }, []);

  const setTopPickToggle = useCallback(
    (id) => {
      const p = programs.find((x) => x.id === id);
      if (!p) return;
      setTopPick((prev) => {
        const next = prev === id ? null : id;
        showToast(next ? p.name + " is your top pick" : "Removed " + p.name + " as top pick");
        return next;
      });
    },
    [programs, showToast]
  );

  const reset = useCallback(() => {
    setQuery("");
    setQ("");
    setField("all");
    setLevel("all");
    setShowShort(false);
    setSelected(null);
  }, []);

  // Body scroll lock while a dialog is open.
  useEffect(() => {
    document.body.style.overflow = sheetOpen || compareOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [sheetOpen, compareOpen]);

  // `inert` on closed dialogs + focus into the opened dialog.
  useEffect(() => {
    if (sheetRef.current) {
      if (sheetOpen) {
        sheetRef.current.removeAttribute("inert");
        const el = sheetRef.current.querySelector("#sheetClose");
        if (el) setTimeout(() => el.focus(), 0);
      } else {
        sheetRef.current.setAttribute("inert", "");
      }
    }
  }, [sheetOpen]);

  useEffect(() => {
    if (compareRef.current) {
      if (compareOpen) {
        compareRef.current.removeAttribute("inert");
        const el = compareRef.current.querySelector("#compareClose");
        if (el) setTimeout(() => el.focus(), 0);
      } else {
        compareRef.current.setAttribute("inert", "");
      }
    }
  }, [compareOpen]);

  // Escape to close + focus trap (Tab) within the open dialog.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        if (compareOpen) {
          closeCompare(true);
          return;
        }
        if (sheetOpen) {
          closeDetail(true);
          return;
        }
      }
      if (e.key === "Tab") {
        const openEl = compareOpen ? compareRef.current : sheetOpen ? sheetRef.current : null;
        if (!openEl) return;
        const focusables = openEl.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [compareOpen, sheetOpen, closeCompare, closeDetail]);

  if (status !== "ready") {
    return (
      <div className="boot">
        {status === "loading" ? (
          <>
            <div className="boot-spinner" aria-hidden="true" />
            <p>Loading programs from the backend…</p>
          </>
        ) : (
          <>
            <h2>Could not load programs</h2>
            <p className="boot-error">{error}</p>
            <p className="boot-hint">
              Start the backend with <code>python -m degreeprograms.cli serve</code> (it serves this UI and the API on the
              same origin), then reload.
            </p>
          </>
        )}
      </div>
    );
  }

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to programs
      </a>

      <Header
        showShort={showShort}
        shortCount={shortCount}
        onOpenProfile={() => setProfileOpen(true)}
        onToggleShort={() => {
          setShowShort((v) => !v);
          setSelected(null);
          showToast(!showShort ? "Showing only shortlisted programs" : "Showing all matched programs");
        }}
      />

      <main id="main">
        <div className="container">
          <Hero count={count} avg={avg} shortCount={shortCount} profile={profile} />

          <MatchMap list={list} selected={selected} onSelect={openDetail} onReset={reset} />

          <section className="panel" aria-labelledby="tableTitle">
            <div className="section-head">
              <h2 id="tableTitle">All matched programs</h2>
              <div className="section-head-actions">
                <p className="hint">Sortable and searchable — your shortlist is saved in this session</p>
                <button
                  type="button"
                  className="btn btn-secondary btn-compare"
                  id="compareBtn"
                  ref={compareBtnRef}
                  disabled={shortCount < 2}
                  title={
                    shortCount < 2
                      ? "Shortlist at least 2 programs to compare them"
                      : "Compare " + shortCount + " shortlisted programs"
                  }
                  onClick={openCompare}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 4v14M18 6v12" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
                    <path d="M3 18h18" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
                  </svg>
                  Compare shortlist <span className="btn-count" id="compareCount">{shortCount}</span>
                </button>
              </div>
            </div>

            <Toolbar
              query={query}
              onQuery={setQuery}
              field={field}
              onField={(v) => {
                setField(v);
                setSelected(null);
              }}
              level={level}
              onLevel={(v) => {
                setLevel(v);
                setSelected(null);
              }}
              fieldOptions={fieldOptions}
              resetActive={resetActive}
              onReset={reset}
              countText={countText}
            />

            {empty ? (
              <div className="empty show" id="listEmpty">
                <h3>No programs match those filters</h3>
                <p>Try a broader search, or clear the filters to see the full list.</p>
                <button className="btn btn-secondary" data-clear onClick={reset}>
                  Reset filters
                </button>
              </div>
            ) : (
              <>
                <ProgramTable
                  list={list}
                  selected={selected}
                  shortSet={short}
                  topPick={topPick}
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={onSort}
                  onOpen={openDetail}
                  onShort={toggleShort}
                  onRowClick={openDetail}
                />
                <ProgramCards
                  list={list}
                  selected={selected}
                  shortSet={short}
                  topPick={topPick}
                  onOpen={openDetail}
                  onShort={toggleShort}
                />
              </>
            )}

            <p className="footnote">
              Sample data for demo — institution names are real; tuition, scores, and match figures are illustrative, not
              verified.
            </p>
          </section>
        </div>
      </main>

      <div className={"scrim" + (sheetOpen ? " open" : "")} id="scrim" onClick={() => closeDetail(true)} />

      <DetailSheet
        program={program}
        detail={activeDetail}
        open={sheetOpen}
        shortSet={short}
        onShort={toggleShort}
        onClose={closeDetail}
        sheetRef={sheetRef}
        shortBtnRef={sheetShortRef}
      />

      <div className={"scrim compare-scrim" + (compareOpen ? " open" : "")} id="compareScrim" onClick={() => closeCompare(true)} />

      <CompareDialog
        open={compareOpen}
        list={shortlistedSorted}
        bestId={compareBestId}
        topPick={topPick}
        onPick={setTopPickToggle}
        onClose={closeCompare}
        compareRef={compareRef}
      />

      <ProfileEditor
        profile={profile}
        open={profileOpen}
        onClose={() => setProfileOpen(false)}
        onSaved={handleProfileSaved}
        onToast={showToast}
      />

      <Toast show={toast.show} msg={toast.msg} />
    </>
  );
}
