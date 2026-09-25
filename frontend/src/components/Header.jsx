import { Brand, User, Star } from "../icons.jsx";

export default function Header({ showShort, shortCount, onToggleShort, onOpenProfile }) {
  const shortCountText = shortCount + " program" + (shortCount === 1 ? "" : "s") + " shortlisted";
  return (
    <header className="site-header">
      <div className="container header-inner">
        <div className="brand">
          <Brand />
          <span>ProgramMatch</span>
        </div>
        <span className="spacer" />
        <button type="button" className="profile-btn" onClick={onOpenProfile}>
          <User />
          <span className="od-nowrap">Your profile</span>
        </button>
        <button
          type="button"
          className="shortlist-btn"
          id="shortlistToggle"
          aria-pressed={showShort ? "true" : "false"}
          aria-label={(showShort ? "Show all programs" : "Show only shortlisted programs") + " · " + shortCountText}
          onClick={onToggleShort}
        >
          <Star size={17} />
          <span id="shortlistLabel">{showShort ? "All programs" : "Shortlist"}</span>
          <span className="badge" id="shortlistBadge" aria-hidden="true">
            {shortCount}
          </span>
        </button>
      </div>
    </header>
  );
}
