type GlyphProps = {
  size?: number;
  className?: string;
};

function glyph(character: string) {
  return function Glyph({ size = 18, className = "" }: GlyphProps) {
    return <span
      aria-hidden="true"
      className={`folio-glyph ${className}`.trim()}
      style={{ fontSize: size }}
    >{character}</span>;
  };
}

export const Activity = glyph("↗");
export const BadgeDollarSign = glyph("$");
export const Banknote = glyph("▱");
export const BarChart3 = glyph("▥");
export const ChartPie = glyph("◔");
export const CircleDollarSign = glyph("¤");
export const Database = glyph("◫");
export const Gauge = glyph("◴");
export const Landmark = glyph("▥");
export const Layers3 = glyph("≋");
export const LoaderCircle = glyph("◌");
export const NotebookTabs = glyph("▤");
export const Plus = glyph("+");
export const RefreshCw = glyph("↻");
export const Settings2 = glyph("⚙");
export const ShieldCheck = glyph("✓");
export const SlidersHorizontal = glyph("≡");
export const Trash2 = glyph("×");
export const TriangleAlert = glyph("!");
export const WalletCards = glyph("▣");
