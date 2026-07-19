export const DEPARTMENT_THEMES: Record<string, {
  label: string;
  accent: string;
  accentLight: string;
  icon: string;
  bgAccent: string;
}> = {
  admin: {
    label: "Admin",
    accent: "#ff7a1a",
    accentLight: "#ffab57",
    icon: "A",
    bgAccent: "rgba(255, 92, 0, 0.14)",
  },
  sales: {
    label: "Sales",
    accent: "#ff8a28",
    accentLight: "#ffba66",
    icon: "S",
    bgAccent: "rgba(255, 112, 0, 0.14)",
  },
  operations: {
    label: "Operations",
    accent: "#ff6900",
    accentLight: "#ff9d45",
    icon: "O",
    bgAccent: "rgba(255, 82, 0, 0.14)",
  },
  finance: {
    label: "Finance",
    accent: "#ff9a35",
    accentLight: "#ffc06e",
    icon: "F",
    bgAccent: "rgba(255, 136, 0, 0.14)",
  },
  executive: {
    label: "Executive",
    accent: "#ff5e12",
    accentLight: "#ff9a5c",
    icon: "E",
    bgAccent: "rgba(255, 72, 0, 0.14)",
  },
};
