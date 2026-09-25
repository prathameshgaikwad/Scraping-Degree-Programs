import { degreeLabel } from "../lib/backend.js";

export default function Hero({ count, avg, shortCount, profile }) {
  const edu = (profile && profile.education) || {};
  const cgpa = edu.cgpa != null ? "CGPA " + edu.cgpa + (edu.cgpa_scale ? "/" + edu.cgpa_scale : "") : null;
  const degree = edu.degree ? degreeLabel(edu.degree) + (edu.field ? " in " + edu.field : "") : null;
  const targets = (profile && profile.target_fields) || [];
  const testing = (profile && profile.testing) || {};
  const ielts = testing.ielts != null ? "IELTS " + testing.ielts : null;

  const chips = [degree, cgpa, ielts, targets.length ? targets.length + " target fields" : null].filter(Boolean);

  return (
    <section className="hero">
      <h1>Programs that fit you best</h1>
      <p className="lede" id="heroProfileText">
        Top university programs matched to your applicant profile — ranked by how well each one fits your background,
        goals, and current standing.
      </p>
      <div className="od-cluster profile-chips" aria-label="Applicant profile">
        {chips.map((c) => (
          <span className="chip chip-meta" key={c}>
            {c}
          </span>
        ))}
      </div>
      <div className="stat-row">
        <div className="od-stat stat">
          <span className="stat-num" id="stCount">
            {count}
          </span>
          <span className="stat-cap">Programs matched</span>
        </div>
        <div className="od-stat stat">
          <span className="stat-num" id="stAvg">
            {avg}%
          </span>
          <span className="stat-cap">Average standing</span>
        </div>
        <div className="od-stat stat">
          <span className="stat-num" id="stShort">
            {shortCount}
          </span>
          <span className="stat-cap">In your shortlist</span>
        </div>
      </div>
    </section>
  );
}
