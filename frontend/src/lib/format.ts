// Shared number formatters so every view renders counts and rates identically.
export const integer = new Intl.NumberFormat("en-US");
export const decimal = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
