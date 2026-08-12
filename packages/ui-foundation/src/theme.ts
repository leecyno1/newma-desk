export type NewmaThemeMode = "light" | "dark";

export interface NewmaThemeSemanticPalette {
  bg: string;
  surface: string;
  surfaceMuted: string;
  surfaceRaised: string;
  border: string;
  borderStrong: string;
  text: string;
  textSoft: string;
  textMuted: string;
  textFaint: string;
  accent: string;
  accentHover: string;
  accentSoft: string;
  accentSurface: string;
  accentContrast: string;
  positive: string;
  negative: string;
  warning: string;
  error: string;
  successText: string;
  successBg: string;
  successBorder: string;
  errorText: string;
  errorBg: string;
  errorBorder: string;
}

export interface NewmaChartPalette {
  gridColor: string;
  textColor: string;
  axisColor: string;
  upColor: string;
  downColor: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  series: string[];
}

export interface NewmaDeskAppearance {
  contractVersion: "1.0";
  mode: NewmaThemeMode;
  cssVars: Record<string, string>;
  semantic: NewmaThemeSemanticPalette;
  charts: NewmaChartPalette;
}

interface NewmaThemeDefinition {
  semantic: NewmaThemeSemanticPalette;
  charts: NewmaChartPalette;
  extraCssVars: Record<string, string>;
}

const themeDefinitions: Record<NewmaThemeMode, NewmaThemeDefinition> = {
  light: {
    semantic: {
      bg: "#f4efe3",
      surface: "#fbf7ef",
      surfaceMuted: "#eae1d0",
      surfaceRaised: "#fffaf1",
      border: "#d8cdbb",
      borderStrong: "#b9aa90",
      text: "#173128",
      textSoft: "#3f5c51",
      textMuted: "#66766e",
      textFaint: "#89958d",
      accent: "#a87432",
      accentHover: "#8d5e25",
      accentSoft: "#ddc79c",
      accentSurface: "#f1e3c6",
      accentContrast: "#173128",
      positive: "#dc2626",
      negative: "#16a34a",
      warning: "#a16207",
      error: "#b91c1c",
      successText: "#166534",
      successBg: "#f0fdf4",
      successBorder: "#bbf7d0",
      errorText: "#991b1b",
      errorBg: "#fef2f2",
      errorBorder: "#fecaca",
    },
    charts: {
      gridColor: "#d8cdbb",
      textColor: "#66766e",
      axisColor: "#b9aa90",
      upColor: "#dc2626",
      downColor: "#16a34a",
      tooltipBg: "#fffaf1",
      tooltipBorder: "#b9aa90",
      tooltipText: "#173128",
      series: ["#a87432", "#3f7667", "#8f6b50", "#77825c", "#a45e52"],
    },
    extraCssVars: {
      "--vibe-sidebar": "#eae1d0",
      "--vibe-sidebar-rail": "#102019",
      "--vibe-sidebar-rail-hover": "#203129",
      "--vibe-sidebar-rail-text": "#f3ecdd",
      "--vibe-surface-hover": "#e2d8c6",
      "--vibe-surface-selected": "#e0d2b5",
    },
  },
  dark: {
    semantic: {
      bg: "#0f1714",
      surface: "#16211c",
      surfaceMuted: "#121d18",
      surfaceRaised: "#1a2821",
      border: "#2a3931",
      borderStrong: "#405146",
      text: "#f3ecdd",
      textSoft: "#cfc7b7",
      textMuted: "#a8b4a5",
      textFaint: "#78847a",
      accent: "#c89a5a",
      accentHover: "#dab47d",
      accentSoft: "#5a452c",
      accentSurface: "#2c2a21",
      accentContrast: "#102019",
      positive: "#f87171",
      negative: "#4ade80",
      warning: "#fbbf24",
      error: "#f87171",
      successText: "#86efac",
      successBg: "#0d2818",
      successBorder: "#166534",
      errorText: "#fca5a5",
      errorBg: "#321417",
      errorBorder: "#7f1d1d",
    },
    charts: {
      gridColor: "#2a3931",
      textColor: "#a8b4a5",
      axisColor: "#405146",
      upColor: "#f87171",
      downColor: "#4ade80",
      tooltipBg: "#1a2821",
      tooltipBorder: "#405146",
      tooltipText: "#f3ecdd",
      series: ["#c89a5a", "#70a596", "#b67b64", "#9da96f", "#cf756b"],
    },
    extraCssVars: {
      "--vibe-sidebar": "#121d18",
      "--vibe-sidebar-rail": "#102019",
      "--vibe-sidebar-rail-hover": "#203129",
      "--vibe-sidebar-rail-text": "#f3ecdd",
      "--vibe-surface-hover": "#203129",
      "--vibe-surface-selected": "#2a382e",
    },
  },
};

const semanticVariableNames: Record<keyof NewmaThemeSemanticPalette, string> = {
  bg: "--vibe-bg",
  surface: "--vibe-surface",
  surfaceMuted: "--vibe-surface-muted",
  surfaceRaised: "--vibe-surface-raised",
  border: "--vibe-border",
  borderStrong: "--vibe-border-strong",
  text: "--vibe-text",
  textSoft: "--vibe-text-soft",
  textMuted: "--vibe-text-muted",
  textFaint: "--vibe-text-faint",
  accent: "--vibe-accent",
  accentHover: "--vibe-accent-hover",
  accentSoft: "--vibe-accent-soft",
  accentSurface: "--vibe-accent-surface",
  accentContrast: "--vibe-accent-contrast",
  positive: "--vibe-positive",
  negative: "--vibe-negative",
  warning: "--vibe-warning",
  error: "--vibe-error",
  successText: "--vibe-success-text",
  successBg: "--vibe-success-bg",
  successBorder: "--vibe-success-border",
  errorText: "--vibe-error-text",
  errorBg: "--vibe-error-bg",
  errorBorder: "--vibe-error-border",
};

function semanticCssVariables(
  semantic: NewmaThemeSemanticPalette,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(semanticVariableNames).map(([key, variable]) => [
      variable,
      semantic[key as keyof NewmaThemeSemanticPalette],
    ]),
  );
}

function newmaAliases(cssVars: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(cssVars).map(([name, value]) => [
      name.replace(/^--vibe-/, "--newma-"),
      value,
    ]),
  );
}

export function createNewmaDeskAppearance(
  mode: NewmaThemeMode,
): NewmaDeskAppearance {
  const definition = themeDefinitions[mode];
  const vibeVariables = {
    ...semanticCssVariables(definition.semantic),
    ...definition.extraCssVars,
    "--vibe-chart-grid": definition.charts.gridColor,
    "--vibe-chart-text": definition.charts.textColor,
    "--vibe-chart-axis": definition.charts.axisColor,
    "--vibe-chart-up": definition.charts.upColor,
    "--vibe-chart-down": definition.charts.downColor,
    "--vibe-chart-tooltip-bg": definition.charts.tooltipBg,
    "--vibe-chart-tooltip-border": definition.charts.tooltipBorder,
    "--vibe-chart-tooltip-text": definition.charts.tooltipText,
    ...Object.fromEntries(
      definition.charts.series.map((value, index) => [
        `--vibe-chart-series-${index + 1}`,
        value,
      ]),
    ),
  };
  return {
    contractVersion: "1.0",
    mode,
    cssVars: { ...vibeVariables, ...newmaAliases(vibeVariables) },
    semantic: { ...definition.semantic },
    charts: { ...definition.charts, series: [...definition.charts.series] },
  };
}

export const newmaThemePalettes = {
  light: createNewmaDeskAppearance("light"),
  dark: createNewmaDeskAppearance("dark"),
} as const;
