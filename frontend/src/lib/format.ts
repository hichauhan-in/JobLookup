export const STAGES: Record<string, string> = {
  saved: "Saved",
  considering: "Considering",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export function label(value?: string | null) {
  if (!value || value === "unknown") return "Not specified";
  return (
    STAGES[value] ||
    value
      .replaceAll("_", " ")
      .replace(/^./, (character) => character.toUpperCase())
  );
}

export function dateValue(value?: string | null) {
  if (!value) return null;
  let normalized = value.replace(" ", "T");
  if (normalized.includes("T") && !/(Z|[+-]\d\d:\d\d)$/i.test(normalized))
    normalized += "Z";
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function dateLabel(value?: string | null) {
  const date = dateValue(value);
  return date
    ? date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Date not published";
}

export function ago(value?: string | null) {
  const date = dateValue(value);
  if (!date) return "Date unknown";
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days < 0) return dateLabel(value);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  return dateLabel(value);
}

export function initials(value: string) {
  return (
    value
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("")
      .toUpperCase() || "JL"
  );
}

export function companyColor(value: string) {
  return (
    [...value].reduce(
      (total, character) => total + character.charCodeAt(0),
      0,
    ) % 6
  );
}

export function salary(
  low?: number | null,
  high?: number | null,
  currency?: string,
) {
  if (!low && !high) return "";
  const format = (value: number) => {
    try {
      return new Intl.NumberFormat("en", {
        ...(currency ? { style: "currency", currency } : {}),
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(value);
    } catch {
      return String(value);
    }
  };
  return low && high
    ? `${format(low)} - ${format(high)}`
    : format(low || high || 0);
}

export function safeLink(value?: string | null) {
  try {
    const url = new URL(value || "");
    return ["http:", "https:"].includes(url.protocol) && !url.username
      ? url.href
      : "";
  } catch {
    return "";
  }
}
