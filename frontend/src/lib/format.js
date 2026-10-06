export const money = (v) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(v || 0));

export const fmtDate = (s) => {
  if (!s) return "";
  const [y, m, d] = s.split("-");
  if (!y || !m || !d) return s;
  return `${m}/${d}/${y}`;
};

export const todayISO = () => new Date().toISOString().slice(0, 10);

export function monthRange(offset = 0) {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() + offset, 1);
  const last = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0);
  const iso = (d) => d.toISOString().slice(0, 10);
  return { start: iso(first), end: iso(last) };
}

// Order funds parent-before-children with a depth for indentation (handles multi-level nesting).
export function orderFunds(funds = []) {
  const byId = Object.fromEntries(funds.map((f) => [f.id, f]));
  const children = {};
  funds.forEach((f) => {
    const pid = f.parent_id && byId[f.parent_id] ? f.parent_id : "__root__";
    (children[pid] = children[pid] || []).push(f);
  });
  const out = [];
  const seen = new Set();
  const walk = (key, depth) => {
    (children[key] || [])
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((f) => {
        if (seen.has(f.id)) return;
        seen.add(f.id);
        out.push({ ...f, depth });
        walk(f.id, depth + 1);
      });
  };
  walk("__root__", 0);
  funds.forEach((f) => {
    if (!seen.has(f.id)) { seen.add(f.id); out.push({ ...f, depth: 0 }); }
  });
  return out;
}

export const fundIndent = (depth) => (depth > 0 ? "\u00A0\u00A0".repeat(depth) + "↳ " : "");
