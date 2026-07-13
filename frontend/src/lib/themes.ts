export const DEPARTMENT_THEMES: Record<string, {
  label: string;
  accent: string;
  accentLight: string;
  icon: string;
  bgAccent: string;
}> = {
  admin: {
    label: "Admin",
    accent: "#7c9dff",
    accentLight: "#a3baff",
    icon: "A",
    bgAccent: "rgba(124, 157, 255, 0.1)",
  },
  sales: {
    label: "Sales",
    accent: "#6dcba1",
    accentLight: "#8fd9b8",
    icon: "S",
    bgAccent: "rgba(109, 203, 161, 0.1)",
  },
  operations: {
    label: "Operations",
    accent: "#d4a574",
    accentLight: "#e0b88a",
    icon: "O",
    bgAccent: "rgba(212, 165, 116, 0.1)",
  },
  finance: {
    label: "Finance",
    accent: "#6bc5d9",
    accentLight: "#8dd4e4",
    icon: "F",
    bgAccent: "rgba(107, 197, 217, 0.1)",
  },
  executive: {
    label: "Executive",
    accent: "#d4829a",
    accentLight: "#e09db2",
    icon: "E",
    bgAccent: "rgba(212, 130, 154, 0.1)",
  },
};
