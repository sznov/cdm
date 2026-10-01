export function numberOrNull(input) {
  if (!input) return null;
  const value = input.value.trim();
  if (value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}
