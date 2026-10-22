const modules = [
  ["global-situation", "全球情报"], ["seven-cycle-research", "周期叠加"],
  ["market-daily", "市场行情"], ["instock-industry-chain", "产业链"],
  ["orchestra-committee", "投决会"],
];
const main = document.querySelector("#main");
const requested = new URL(location.href).searchParams.get("mod") || "global-situation";
const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const svg = (tag, attrs = {}, text) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
};
const navigation = document.querySelector("#navigation");
for (const [id, label] of modules) {
  const link = el("a", label);
  link.href = `/demo/?mod=${encodeURIComponent(id)}`;
  if (id === requested) link.setAttribute("aria-current", "page");
  navigation.append(link);
}

function makeChart(chart) {
  const panel = el("section", undefined, "chart-panel");
  panel.append(el("p", "OBSERVATION / 观察视图", "eyebrow"), el("h2", chart.title), el("p", chart.subtitle, "muted"));
  const stage = el("div", undefined, `chart-stage ${chart.type}`);
  const note = el("p", chart.notes?.[0] || "选择窗口查看不同长度的历史序列。", "chart-note");
  let buttons = [];
  const select = index => {
    buttons.forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
    if (chart.notes) note.textContent = chart.notes[index];
  };
  const controls = el("div", undefined, "chart-controls");
  if (chart.type === "line") {
    const draw = count => {
      stage.replaceChildren();
      const values = chart.values.slice(-count), labels = chart.labels.slice(-count);
      const picture = svg("svg", { viewBox: "0 0 700 290", role: "img", "aria-label": chart.seriesLabel + "，历史快照非实时" });
      const padding = Math.max((Math.max(...values) - Math.min(...values)) * 0.12, 0.01);
      const low = Math.min(...values) - padding, high = Math.max(...values) + padding;
      const decimals = Math.max(...values.map(Math.abs)) < 10 ? 3 : 0;
      const x = i => 55 + i * 610 / (values.length - 1), y = v => 245 - (v - low) * 210 / (high - low);
      for (let i = 0; i <= 4; i++) {
        const value = low + (high - low) * i / 4;
        picture.append(svg("line", { x1: 55, x2: 665, y1: y(value), y2: y(value), class: "grid" }), svg("text", { x: 44, y: y(value) + 4, "text-anchor": "end", class: "axis" }, value.toFixed(decimals)));
      }
      const points = values.map((value, i) => `${x(i)},${y(value)}`).join(" ");
      picture.append(svg("polygon", { points: `55,245 ${points} 665,245`, class: "area" }), svg("polyline", { points, class: "price-line" }));
      values.forEach((value, i) => {
        const dot = svg("circle", { cx: x(i), cy: y(value), r: 4, class: "price-dot" });
        dot.append(svg("title", {}, `${labels[i]}：${value} ${chart.unit}（归档）`));
        picture.append(dot);
        if (i === 0 || i === values.length - 1 || i % 5 === 0) picture.append(svg("text", { x: x(i), y: 270, "text-anchor": "middle", class: "axis" }, labels[i]));
      });
      stage.append(picture);
      note.textContent = `${labels[0]} 至 ${labels.at(-1)}，${count} 期归档；区间 ${Math.min(...values)}–${Math.max(...values)} ${chart.unit}。不是实时更新。`;
    };
    [...new Set([chart.values.length, Math.min(12, chart.values.length)])].forEach((count, index) => {
      const button = el("button", `${count} 期`);
      button.type = "button";
      button.addEventListener("click", () => { select(index); draw(count); });
      controls.append(button); buttons.push(button);
    });
    draw(chart.values.length);
  } else if (chart.type === "radar") {
    const picture = svg("svg", { viewBox: "0 0 700 340", role: "img", "aria-label": "七维合成周期雷达，非当前市场状态" });
    const point = (i, radius) => [350 + Math.sin(i * 2 * Math.PI / 7) * radius, 170 - Math.cos(i * 2 * Math.PI / 7) * radius];
    [0.25, 0.5, 0.75, 1].forEach(scale => picture.append(svg("polygon", { points: chart.values.map((_, i) => point(i, scale * 125).join(",")).join(" "), class: "radar-grid" })));
    chart.labels.forEach((label, i) => {
      const [x, y] = point(i, 150);
      const [endX, endY] = point(i, 125);
      picture.append(svg("line", { x1: 350, y1: 170, x2: endX, y2: endY, class: "grid" }), svg("text", { x, y: y + 4, "text-anchor": "middle", class: "radar-label" }, label));
      const button = el("button", `${label} · ${chart.values[i]}`); button.type = "button";
      button.addEventListener("click", () => select(i)); buttons.push(button); controls.append(button);
    });
    picture.append(svg("polygon", { points: chart.values.map((value, i) => point(i, value * 1.25).join(",")).join(" "), class: "radar-shape" }));
    stage.append(picture);
  } else {
    chart.labels.forEach((label, i) => {
      const button = el("button", undefined, "observation"); button.type = "button";
      button.append(el("span", String(i + 1).padStart(2, "0"), "number"), el("strong", label));
      if (chart.type === "bars") {
        const meter = el("progress"); meter.max = chart.max; meter.value = chart.values[i];
        meter.setAttribute("aria-label", `${label}${chart.unit}`);
        button.append(meter, el("span", `${chart.values[i]} ${chart.unit}`, "figure"));
      } else button.append(el("span", chart.type === "committee" ? "角色职责 →" : "研究要点 →", "node-link"));
      button.addEventListener("click", () => select(i)); buttons.push(button); stage.append(button);
    });
  }
  select(0);
  const details = el("details", undefined, "data-table");
  details.append(el("summary", "查看完整数据表与口径"));
  const table = el("table");
  const caption = el("caption", "完整只读数据表；性质和时点以页面说明为准，不代表实时观察");
  const head = el("thead"), headRow = el("tr");
  headRow.append(el("th", "观察项"), el("th", ["chain", "committee"].includes(chart.type) ? "序号（非评级）" : chart.unit || "数值"));
  head.append(headRow); table.append(caption, head);
  const body = el("tbody");
  chart.labels.forEach((label, i) => { const row = el("tr"); row.append(el("td", label), el("td", String(chart.values[i]))); body.append(row); });
  table.append(body); details.append(table);
  panel.append(controls, stage, note, details);
  return panel;
}

function render(payload) {
  const content = payload.content;
  document.title = `${content.title} · 公开只读 · Newma Desk`;
  main.replaceChildren(); main.dataset.moduleId = payload.moduleId;
  const hero = el("section", undefined, "hero");
  const heading = el("div");
  heading.append(el("p", content.eyebrow, "eyebrow"), el("h1", content.title), el("p", content.description, "description"));
  hero.append(heading, el("span", "READ ONLY", "stamp"));
  const notice = el("aside", content.notice, "notice"); notice.setAttribute("aria-label", "数据性质说明");
  const metrics = el("section", undefined, "metrics");
  metrics.setAttribute("aria-label", "展示范围");
  for (const metric of content.metrics) {
    const card = el("article"); card.append(el("p", metric.label, "metric-label"), el("strong", metric.value), el("p", metric.detail, "muted")); metrics.append(card);
  }
  const layout = el("div", undefined, "workspace");
  const side = el("div", undefined, "research-notes");
  for (const section of content.sections) {
    const card = el("section", undefined, "note-card"); card.append(el("h2", section.title));
    const list = el("ul"); section.items.forEach(text => list.append(el("li", text))); card.append(list); side.append(card);
  }
  layout.append(makeChart(content.chart), side);
  const sources = el("section", undefined, "sources");
  sources.append(el("h2", payload.dataKind === "illustrative" ? "方法参考 · 非数据接入证明" : "公开来源与历史快照口径"));
  for (const source of content.sources) {
    const link = el("a", source.title + " ↗"); link.href = source.url; link.target = "_blank"; link.rel = "noopener noreferrer"; sources.append(link);
  }
  sources.append(el("p", `${payload.disclaimer} 观测/采集时点：${payload.asOf || "无（方法示例）"}。内容版本 ${payload.contentVersion}。`, "muted"));
  if (!payload.ready) sources.append(el("p", `未标为材料就绪：${payload.reason}`, "muted"));
  main.append(hero, notice, metrics, layout, sources);
}

async function load() {
  main.replaceChildren(el("p", "正在读取公开演示内容…", "loading"));
  try {
    if (!modules.some(([id]) => id === requested)) throw new Error("此页面不在五个公开演示入口中。");
    const response = await fetch(`/demo/api/modules/${encodeURIComponent(requested)}`, {
      credentials: "omit", redirect: "error", cache: "no-store", signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error(`公开内容暂不可用（${response.status}）。`);
    const payload = await response.json();
    if (payload.moduleId !== requested || payload.mode !== "public-readonly" || !["illustrative", "public-snapshot", "research-snapshot"].includes(payload.dataKind)) throw new Error("公开内容契约不匹配，已停止展示。");
    render(payload);
  } catch (error) {
    main.replaceChildren(el("h1", "暂未加载公开内容"), el("p", error instanceof Error ? error.message : "请求失败", "notice"));
    const retry = el("button", "重新读取公开内容", "retry"); retry.type = "button"; retry.addEventListener("click", load); main.append(retry);
  }
}
void load();
