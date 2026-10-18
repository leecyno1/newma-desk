import { ChevronLeft, ChevronRight } from "lucide-react";
import type { CalendarBasis, PolicyCalendarEntry } from "./calendar";
import { shiftPolicyMonth } from "./calendar";

export function PolicyCalendar({ month, today, basis, mode, entries, selectedId, onMonth, onBasis, onMode, onSelect }: {
  month: string; today: string; basis: CalendarBasis; mode: "month" | "agenda";
  entries: PolicyCalendarEntry[]; selectedId: string | null;
  onMonth(month: string): void; onBasis(basis: CalendarBasis): void;
  onMode(mode: "month" | "agenda"): void; onSelect(entry: PolicyCalendarEntry): void;
}) {
  const year = Number(month.slice(0, 4));
  const monthNumber = Number(month.slice(5, 7));
  const leading = (new Date(year, monthNumber - 1, 1).getDay() + 6) % 7;
  const days = new Date(year, monthNumber, 0).getDate();
  const cells: Array<number | null> = [...Array.from({ length: leading }, () => null), ...Array.from({ length: days }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const renderEntry = (entry: PolicyCalendarEntry) => <button type="button" key={entry.id}
    className={`calendar-event ${entry.kind}${selectedId === entry.id ? " selected" : ""}`}
    onClick={() => onSelect(entry)} title={`${entry.date} · ${entry.label} · ${entry.event.title}`}>
    <b>{entry.label}</b><span>{entry.event.title}</span>
  </button>;
  return <section className="policy-calendar" aria-label="政策日期工作台">
    <div className="calendar-controls">
      <button type="button" aria-label="上一月" onClick={() => onMonth(shiftPolicyMonth(month, -1))}><ChevronLeft /></button>
      <input type="month" aria-label="政策月份" value={month} onChange={(e) => { if (e.target.value) onMonth(e.target.value); }} />
      <button type="button" aria-label="下一月" onClick={() => onMonth(shiftPolicyMonth(month, 1))}><ChevronRight /></button>
      <button type="button" onClick={() => onMonth(today.slice(0, 7))}>本月</button>
      <div className="calendar-modes"><button type="button" aria-pressed={mode === "month"} onClick={() => onMode("month")}>月历</button><button type="button" aria-pressed={mode === "agenda"} onClick={() => onMode("agenda")}>议程</button></div>
    </div>
    <div className="calendar-basis" aria-label="日期口径">{([ ["all", "全部日期"], ["publication", "发布记录"], ["effective", "明确施行"], ["window", "日程窗口"] ] as const).map(([key, label]) => <button type="button" aria-pressed={basis === key} onClick={() => onBasis(key)} key={key}>{label}</button>)}<span>{entries.length} 个日期节点</span></div>
    <p className="calendar-caveat">施行日来自已读取原文；预期窗口不是官方预约。未载入不代表没有政策。</p>
    {mode === "month" ? <>
      <div className="calendar-weekdays">{["一", "二", "三", "四", "五", "六", "日"].map((d) => <span key={d}>{d}</span>)}</div>
      <div className="calendar-grid">{cells.map((day, i) => {
        const date = day ? `${month}-${String(day).padStart(2, "0")}` : "";
        return <div key={i} className={`calendar-day${date === today ? " today" : ""}${!day ? " outside" : ""}`}>
          {day ? <time dateTime={date}>{day}</time> : null}{entries.filter((entry) => entry.date === date).map(renderEntry)}
        </div>;
      })}</div>
    </> : <div className="calendar-agenda">{entries.map((entry) => <div key={entry.id}><time>{entry.date.slice(5)}</time>{renderEntry(entry)}</div>)}</div>}
    {!entries.length ? <div className="empty-state">本月暂无已载入的匹配日期；可切换月份或日期口径。</div> : null}
  </section>;
}
