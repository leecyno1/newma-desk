import type { Industry } from "./research";

const SHORT_NAMES: Record<string, string> = {
  "煤炭开采和洗选业": "煤炭采洗", "石油和天然气开采业": "油气开采", "黑色金属矿采选业": "黑色采矿", "有色金属矿采选业": "有色采矿",
  "非金属矿采选业": "非金属采矿", "开采专业及辅助性活动": "开采辅助", "其他采矿业": "其他采矿", "农副食品加工业": "农副食品",
  "食品制造业": "食品制造", "酒、饮料和精制茶制造业": "酒饮料茶", "烟草制品业": "烟草", "纺织业": "纺织",
  "纺织服装、服饰业": "纺织服装", "皮革、毛皮、羽毛及其制品和制鞋业": "皮革制鞋", "木材加工和木、竹、藤、棕、草制品业": "木竹加工",
  "家具制造业": "家具", "造纸和纸制品业": "造纸", "印刷和记录媒介复制业": "印刷复制", "文教、工美、体育和娱乐用品制造业": "文教文体",
  "石油、煤炭及其他燃料加工业": "燃料加工", "化学原料和化学制品制造业": "化学原料制品", "医药制造业": "医药", "化学纤维制造业": "化纤",
  "橡胶和塑料制品业": "橡塑", "非金属矿物制品业": "非金属制品", "黑色金属冶炼和压延加工业": "黑色冶炼", "有色金属冶炼和压延加工业": "有色冶炼",
  "金属制品业": "金属制品", "通用设备制造业": "通用设备", "专用设备制造业": "专用设备", "汽车制造业": "汽车",
  "铁路、船舶、航空航天和其他运输设备制造业": "铁路船舶航空", "电气机械和器材制造业": "电气机械", "计算机、通信和其他电子设备制造业": "计算机通信电子",
  "仪器仪表制造业": "仪器仪表", "其他制造业": "其他制造", "废弃资源综合利用业": "废弃资源利用", "金属制品、机械和设备修理业": "金属机械修理",
  "电力、热力生产和供应业": "电力热力", "燃气生产和供应业": "燃气供应", "水的生产和供应业": "水供应",
};
export const industryLabel = (name: string) => SHORT_NAMES[name] ?? name;
type Box = {x: number; y: number; width: number; height: number};
const overlaps = (a: Box, b: Box) => a.x < b.x + b.width + 4 && a.x + a.width + 4 > b.x && a.y < b.y + b.height + 4 && a.y + a.height + 4 > b.y;

export function scatterLayout(rows: Industry[], width: number, height: number, scope: Industry[] = rows) {
  const usable = rows.filter(row => row.revenueYoy != null && row.profitYoy != null);
  const comparable = scope.filter(row => row.revenueYoy != null && row.profitYoy != null);
  const extentX = Math.max(10, ...comparable.map(row => Math.abs(row.revenueYoy!))) * 1.12;
  const extentY = Math.max(10, ...comparable.map(row => Math.abs(row.profitYoy!))) * 1.12;
  const bounds = {left: 60, right: width - 24, top: 52, bottom: height - 64};
  const centerX = (bounds.left + bounds.right) / 2, centerY = (bounds.top + bounds.bottom) / 2;
  const points = usable.map(row => ({row, label: industryLabel(row.name),
    x: centerX + row.revenueYoy! / extentX * (bounds.right - bounds.left) / 2,
    y: centerY - row.profitYoy! / extentY * (bounds.bottom - bounds.top) / 2,
  })).sort((a, b) => a.y - b.y || a.x - b.x || a.row.name.localeCompare(b.row.name));
  const occupied: Box[] = points.map(point => ({x: point.x - 6, y: point.y - 6, width: 12, height: 12}));
  const placed = points.map(point => {
    const labelWidth = point.label.length * 12 + 10;
    const candidates: Box[] = [];
    // Prefer a nearby left/right label; use the free plot area for dense clusters.
    for (let y = bounds.top; y <= bounds.bottom - 24; y += 28) {
      for (const x of [point.x + 10, point.x - labelWidth - 10]) candidates.push({x, y, width: labelWidth, height: 24});
      for (let x = bounds.left; x <= bounds.right - labelWidth; x += 24) candidates.push({x, y, width: labelWidth, height: 24});
    }
    const distance = (box: Box) => Math.max(box.x - point.x, point.x - box.x - box.width, 0) ** 2 + (box.y + box.height / 2 - point.y) ** 2;
    candidates.sort((a, b) => distance(a) - distance(b));
    const labelBox = candidates.find(box => box.x >= bounds.left && box.x + box.width <= bounds.right && !occupied.some(other => overlaps(box, other)));
    if (labelBox) occupied.push(labelBox);
    return {...point, labelBox: labelBox ?? null};
  });
  return {points: placed, bounds, centerX, centerY, extentX, extentY};
}
