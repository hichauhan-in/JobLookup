// Presentation helpers. Anything that turns data into words a person reads.

//: SQLite writes "YYYY-MM-DD HH:MM:SS" in UTC and marks neither of those facts,
//: so a browser would otherwise read it as local time and be hours out.
export function utc(stamp) {
  return stamp ? `${String(stamp).replace(" ", "T")}Z` : null;
}

//: `fresh` is what to say for anything under an hour old. It reads as "just
//: posted" for a job, but a status you changed a minute ago was not posted.
export function relativeDate(iso, fresh = "just posted") {
  if (!iso) return "date unknown";
  const posted = new Date(iso);
  if (Number.isNaN(posted.getTime())) return "date unknown";
  const hours = (Date.now() - posted.getTime()) / 3_600_000;
  if (hours < 1) return fresh;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return posted.toLocaleDateString();
}

export function percent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

//: Token counts run to six digits. Nobody reads those, and the exact figure is
//: an estimate anyway, so the magnitude is the honest thing to show.
export function humanTokens(tokens) {
  const n = Number(tokens || 0);
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export function salary(job) {
  const { salary_min: low, salary_max: high, salary_currency: currency } = job;
  if (!low && !high) return "";
  const symbol = { USD: "$", GBP: "£", EUR: "€", INR: "₹" }[currency] || (currency ? `${currency} ` : "");
  const round = (value) => (value >= 1000 ? `${Math.round(value / 1000)}k` : Math.round(value));
  if (low && high) return `${symbol}${round(low)} - ${symbol}${round(high)}`;
  return `${symbol}${round(low || high)}`;
}

export function workMode(value) {
  return { remote: "Remote", hybrid: "Hybrid", onsite: "On site" }[value] || "";
}

export function bandLabel(band) {
  return { strong: "Strong", good: "Good", stretch: "Stretch", rejected: "Ruled out" }[band] || band || "Unscored";
}

export function plural(count, word, suffix = "s") {
  return `${count} ${word}${count === 1 ? "" : suffix}`;
}

export function truncate(text, limit) {
  const value = String(text || "");
  return value.length > limit ? `${value.slice(0, limit - 1).trimEnd()}...` : value;
}

/** A minimal Markdown renderer — enough for tailored CVs and prep sheets. */
export function markdown(source) {
  const escaped = String(source || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const lines = escaped.split("\n");
  const out = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
  };

  for (const line of lines) {
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 1, 5);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    closeList();
    if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  return out.join("\n");
}

function inline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}
