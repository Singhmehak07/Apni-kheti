export const rs = (n) => (n == null ? "—" : "₹" + Math.round(n).toLocaleString("en-IN"));
export const num = (n, d = 1) => (n == null ? "—" : Number(n).toLocaleString("en-IN", { maximumFractionDigits: d }));
export const fill = (s, vars = {}) => s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? ""));
