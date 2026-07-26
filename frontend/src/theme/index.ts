export const theme = {
  colors: {
    primary: "#0EA5E9",
    background: "#F8FAFC",
    card: "#FFFFFF",
    text: "#0F172A",
    muted: "#64748B",
    border: "#E2E8F0",
    danger: "#DC2626",
  },
  spacing: (units: number) => units * 8,
  radius: 12,
};

export type Theme = typeof theme;
