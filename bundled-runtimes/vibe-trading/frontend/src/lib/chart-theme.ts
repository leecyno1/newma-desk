function css(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function hslToHex(hsl: string): string {
  if (!hsl) return "";
  const [h, s, l] = hsl.split(/\s+/).map(parseFloat);
  if (isNaN(h)) return "";
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const color = l / 100 - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * color).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function cssHex(name: string, fallback: string): string {
  const value = css(name);
  if (/^#[\da-f]{6}$/i.test(value)) return value;
  return hslToHex(value) || fallback;
}

function withAlpha(color: string, alpha: string): string {
  return /^#[\da-f]{6}$/i.test(color) ? `${color}${alpha}` : color;
}

function isChinese(): boolean {
  return (document.documentElement.lang || navigator.language || "").startsWith("zh");
}

let _cache: ReturnType<typeof buildTheme> | null = null;
let _cacheKey = "";

function buildTheme() {
  const cn = isChinese();
  const isDark = document.documentElement.classList.contains("dark");

  const successHex = cssHex("--success", "#16a34a");
  const dangerHex = cssHex("--danger", "#b91c1c");
  const infoHex = cssHex("--info", isDark ? "#a8b4a5" : "#3f5c51");
  const warningHex = cssHex("--warning", isDark ? "#dab47d" : "#a16207");
  const gridHex = cssHex("--chart-grid", isDark ? "#121d18" : "#eae1d0");
  const textHex = cssHex("--chart-text", isDark ? "#a8b4a5" : "#66766e");
  const axisHex = cssHex("--chart-axis", isDark ? "#405146" : "#b9aa90");
  const tooltipBg = cssHex("--chart-tooltip-bg", isDark ? "#1a2821" : "#fffaf1");
  const tooltipBorder = cssHex("--chart-tooltip-border", isDark ? "#405146" : "#b9aa90");
  const tooltipText = cssHex("--chart-tooltip-text", isDark ? "#f3ecdd" : "#173128");
  const markerText = cssHex("--primary-foreground", "#173128");
  const seriesColors = [
    cssHex("--chart-series-1", isDark ? "#c89a5a" : "#a87432"),
    cssHex("--chart-series-2", isDark ? "#70a596" : "#3f7667"),
    cssHex("--chart-series-3", isDark ? "#b67b64" : "#8f6b50"),
    cssHex("--chart-series-4", isDark ? "#9da96f" : "#77825c"),
    cssHex("--chart-series-5", isDark ? "#cf756b" : "#a45e52"),
    cssHex("--chart-series-6", isDark ? "#78847a" : "#66766e"),
    cssHex("--chart-series-7", isDark ? "#dab47d" : "#c88964"),
  ];
  const correlationColors = [
    cssHex("--chart-correlation-negative-strong", isDark ? "#5d8d79" : "#315a4a"),
    cssHex("--chart-correlation-negative", isDark ? "#8cad9f" : "#779489"),
    cssHex("--chart-correlation-neutral", isDark ? "#1a2821" : "#f4efe3"),
    cssHex("--chart-correlation-positive", isDark ? "#aa8654" : "#d7b27d"),
    cssHex("--chart-correlation-positive-strong", isDark ? "#dda759" : "#9a5d25"),
  ];

  const positiveHex = cssHex("--financial-positive", dangerHex);
  const negativeHex = cssHex("--financial-negative", successHex);

  // Locale-aware candlestick colors: China = red up / green down.
  const upHex = cn ? positiveHex : negativeHex;
  const downHex = cn ? negativeHex : positiveHex;

  return {
    gridColor: gridHex,
    textColor: textHex,
    axisColor: axisHex,
    upColor: upHex,
    downColor: downHex,
    seriesColors,
    correlationColors,
    maColors: seriesColors.slice(0, 3),
    bollColor: withAlpha(seriesColors[1], "80"),
    volumeUp: withAlpha(upHex, "66"),
    volumeDown: withAlpha(downHex, "66"),
    infoColor: infoHex,
    warningColor: warningHex,
    markerText,
    tooltipBg: withAlpha(tooltipBg, "f5"),
    tooltipBorder,
    tooltipText,
  };
}

export function getChartTheme() {
  const root = document.documentElement;
  const paletteKey = [
    "--success",
    "--danger",
    "--warning",
    "--info",
    "--financial-positive",
    "--financial-negative",
    "--chart-grid",
    "--chart-text",
    "--chart-axis",
    "--chart-tooltip-bg",
    "--chart-tooltip-border",
    "--chart-tooltip-text",
    "--chart-series-1",
    "--chart-series-2",
    "--chart-series-3",
    "--chart-series-4",
    "--chart-series-5",
    "--chart-series-6",
    "--chart-series-7",
  ].map(css).join("|");
  const key = `${root.className}|${root.dataset.theme || ""}|${root.dataset.vibedeskTheme || ""}|${root.lang || navigator.language}|${paletteKey}`;
  if (_cache && _cacheKey === key) return _cache;
  _cache = buildTheme();
  _cacheKey = key;
  return _cache;
}
