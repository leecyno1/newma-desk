import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import {
  Activity, Radar, LayoutGrid, Wallet, Settings, Search, NotebookPen,
  Moon, Sun, ChevronsLeft, ChevronsRight, LineChart, Github, UserRound,
  Cog, Cpu, Database, Cable, Rocket, FlaskConical, Star, FileText, Menu, X,
  Globe, CalendarDays, Filter, PieChart, BookOpen, Scale, Calculator, Target,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDarkMode } from "@/hooks/useDarkMode";

const APP_VERSION = "v0.1.3";
const REPO_URL = "https://github.com/simonlin1212/Vibe-Research";
const SITE_URL = "https://www.simonlin.net"; // 作者主页

// 仅管理本项目独立入口；Desk 嵌入导航仍由宿主编译。
const NAV_GROUPS = [
  { label: "市场与机会", items: [
    { to: "/daily-review", icon: Activity, label: "每日复盘" },
    { to: "/intel", icon: Radar, label: "新闻与舆情" },
    { to: "/macro-monitor", icon: Globe, label: "宏观观察" },
    { to: "/catalyst-calendar", icon: CalendarDays, label: "催化剂日历" },
    { to: "/idea-funnel", icon: Filter, label: "研究机会池" },
  ] },
  { label: "资产与公司", items: [
    { to: "/sectors", icon: LayoutGrid, label: "产业图谱" },
    { to: "/stock-data", icon: Search, label: "个股数据" },
    { to: "/etf-research", icon: PieChart, label: "ETF 研究" },
    { to: "/earnings-workbench", icon: BookOpen, label: "财报研究" },
    { to: "/peer-comparison", icon: Scale, label: "同业比较" },
    { to: "/valuation-workbench", icon: Calculator, label: "预测与估值" },
  ] },
  { label: "跟踪与沉淀", items: [
    { to: "/watchlist", icon: Star, label: "自选股" },
    { to: "/portfolio", icon: Wallet, label: "我的持仓" },
    { to: "/thesis-tracker", icon: Target, label: "投资逻辑" },
    { to: "/research-memo", icon: NotebookPen, label: "研究备忘录" },
    { to: "/my-reports", icon: FileText, label: "研究档案" },
    { to: "/notes", icon: NotebookPen, label: "研究记录" },
  ] },
  { label: "系统", items: [
    { to: "/settings", icon: Settings, label: "接入 AI" },
  ] },
];
const NAV = NAV_GROUPS.flatMap(group => group.items);

// 在产业研究页面展开，避免挤占其他研究入口。
const SECTOR_LINKS = [
  { to: "/sectors/humanoid", icon: Cog, label: "人形机器人" },
  { to: "/sectors/ai-computing", icon: Cpu, label: "AI 算力" },
  { to: "/sectors/hbm", icon: Database, label: "HBM" },
  { to: "/sectors/cpo", icon: Cable, label: "光模块与光互联" },
  { to: "/sectors/business-space", icon: Rocket, label: "商业航天" },
  { to: "/sectors/ai-pharma", icon: FlaskConical, label: "生物医药" },
];

export function Layout() {
  const { pathname } = useLocation();
  const { dark, toggle } = useDarkMode();
  const [desktopCollapsed, setCollapsed] = useState(() => localStorage.getItem("vr-sidebar") === "collapsed");
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 767px)").matches);
  const [mobileOpen, setMobileOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const collapsed = !mobile && desktopCollapsed;
  const embedded = window.parent !== window;

  useEffect(() => {
    localStorage.setItem("vr-sidebar", desktopCollapsed ? "collapsed" : "expanded");
  }, [desktopCollapsed]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const change = (event: MediaQueryListEvent) => {
      dialogRef.current?.close();
      setMobileOpen(false);
      setMobile(event.matches);
    };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);

  useEffect(() => { setMobileOpen(false); }, [pathname]);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (mobileOpen && !dialog.open) dialog.showModal();
    else if (!mobileOpen && dialog.open) dialog.close();
  }, [mobileOpen, mobile]);

  const sidebar = <aside className={cn(
        "glass flex shrink-0 flex-col rounded-2xl",
        mobile ? "h-full w-full" : "z-10 m-2 transition-[width] duration-200 motion-reduce:transition-none",
        !mobile && (collapsed ? "w-14" : "w-60"),
      )}>
        {mobile && <div className="flex items-center justify-between border-b border-border/50 px-4 py-2">
          <h2 className="text-sm font-semibold">研究导航</h2>
          <button autoFocus aria-label="关闭导航" onClick={() => setMobileOpen(false)} className="rounded-lg p-3 text-muted-foreground hover:bg-muted/50"><X className="h-5 w-5" /></button>
        </div>}
        {/* Brand */}
        <div className={cn("border-b border-border/50", collapsed ? "flex justify-center p-3" : "p-4")}>
          <Link to="/daily-review" aria-label="Newma-Trading 首页" onClick={() => setMobileOpen(false)} className={cn("flex items-center", collapsed ? "justify-center" : "gap-2")}>
            <LineChart className="h-6 w-6 shrink-0 text-primary text-glow" />
            {!collapsed && (
              <span className="text-lg font-extrabold tracking-tight">
                Newma-<span className="text-primary">Trading</span>
              </span>
            )}
          </Link>
          {!collapsed && <p className="mt-1 text-[11px] text-muted-foreground">Research Module · A股/美股/港股</p>}
        </div>

        {/* Nav */}
        <nav aria-label="研究页面" onClick={(event) => { if ((event.target as Element).closest("a")) setMobileOpen(false); }} className={cn("min-h-0 flex-1 space-y-1 overflow-auto overscroll-contain", collapsed ? "p-1.5" : "p-2.5")}>
          {NAV_GROUPS.map(group => <section key={group.label} aria-label={group.label} className="mb-2">
            <h2 className={collapsed ? "sr-only" : "px-3 pb-1 pt-3 text-[11px] font-medium tracking-wide text-muted-foreground"}>{group.label}</h2>
            {group.items.map(({ to, icon: Icon, label }) => {
            const active = pathname === to;
            return (
              <div key={to}>
                <Link
                  to={to}
                  aria-label={label}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? label : undefined}
                  className={cn(
                    "flex items-center rounded-lg text-sm transition-colors",
                    collapsed ? "justify-center p-2.5" : "gap-2.5 px-3 py-2.5",
                    active
                      ? "bg-primary/15 font-medium text-primary shadow-glow"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && label}
                </Link>

                {/* 产业页下方：常看行业快捷入口 */}
                {to === "/sectors" && (pathname === to || pathname.startsWith(`${to}/`)) && (
                  <div className={cn("mt-1 space-y-0.5", !collapsed && "ml-4 border-l border-border/40 pl-1.5")}>
                    {SECTOR_LINKS.map(({ to: st, icon: SIcon, label: slabel }) => {
                      const sactive = pathname === st;
                      return (
                        <Link
                          key={st}
                          to={st}
                          aria-label={slabel}
                          aria-current={sactive ? "page" : undefined}
                          title={collapsed ? slabel : undefined}
                          className={cn(
                            "flex items-center rounded-lg transition-colors",
                            collapsed ? "justify-center p-2" : "gap-2 px-2.5 py-1.5 text-[13px]",
                            sactive
                              ? "bg-primary/10 font-medium text-primary"
                              : "text-muted-foreground/80 hover:bg-muted/40 hover:text-foreground",
                          )}
                        >
                          <SIcon className="h-3.5 w-3.5 shrink-0" />
                          {!collapsed && slabel}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}</section>)}
        </nav>

        {/* Footer */}
        <div className={cn("border-t border-border/50", collapsed ? "flex flex-col items-center gap-2 p-2" : "space-y-2 p-3")}>
          {collapsed ? (
            <>
              <button onClick={toggle} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title={dark ? "亮色" : "暗色"}>
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <a href={SITE_URL} target="_blank" rel="noreferrer" className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="联系作者">
                <UserRound className="h-4 w-4" />
              </a>
              <button onClick={() => setCollapsed(false)} className="rounded p-1.5 text-muted-foreground transition-colors hover:text-foreground" title="展开">
                <ChevronsRight className="h-4 w-4" />
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <button onClick={toggle} className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
                  {dark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
                  {dark ? "亮色" : "暗色"}
                </button>
                <div className="flex items-center gap-2">
                  <a href={SITE_URL} target="_blank" rel="noreferrer" className="text-muted-foreground transition-colors hover:text-foreground" title="联系作者">
                    <UserRound className="h-3.5 w-3.5" />
                  </a>
                  <a href={REPO_URL} target="_blank" rel="noreferrer" className="text-muted-foreground transition-colors hover:text-foreground" title="GitHub">
                    <Github className="h-3.5 w-3.5" />
                  </a>
                  {!mobile && <button onClick={() => setCollapsed(true)} className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground" title="收起">
                    <ChevronsLeft className="h-3.5 w-3.5" />
                  </button>}
                </div>
              </div>
              <a href={SITE_URL} target="_blank" rel="noreferrer" className="block text-[11px] text-primary/80 transition-colors hover:text-primary">
                联系作者 · simonlin.net
              </a>
              <p className="text-[11px] leading-relaxed text-muted-foreground/60">
                {APP_VERSION} · 不荐股 · 不预测 · 无倾向
              </p>
            </>
          )}
        </div>
      </aside>;

  return (
    <div className="flex h-dvh min-h-0">
      {!embedded && (mobile ? (
        <dialog ref={dialogRef} id="research-navigation" aria-label="研究导航" aria-modal="true"
          onCancel={() => setMobileOpen(false)} onClose={() => setMobileOpen(false)}
          onClick={(event) => { if (event.target === event.currentTarget) setMobileOpen(false); }}
          className="m-2 h-[calc(100dvh-1rem)] max-h-none w-80 max-w-[calc(100vw-1rem)] overflow-hidden rounded-2xl border border-border bg-card p-0 text-foreground backdrop:bg-foreground/30">
          {sidebar}
        </dialog>
      ) : sidebar)}
      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        {!embedded && mobile && <header className="flex shrink-0 items-center gap-3 border-b border-border bg-card px-3 py-2">
          <button aria-label="打开导航" aria-controls="research-navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)} className="rounded-lg border border-border p-3 text-primary hover:bg-muted/50"><Menu className="h-5 w-5" /></button>
          <span className="text-sm font-semibold">{[...NAV, ...SECTOR_LINKS].find(item => item.to === pathname)?.label || "综合投研"}</span>
        </header>}
        <main className="min-h-0 min-w-0 flex-1 overflow-auto">
          <div className="mx-auto max-w-6xl px-3 py-4 sm:px-6 sm:py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
