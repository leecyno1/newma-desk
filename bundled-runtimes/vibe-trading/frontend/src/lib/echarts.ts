import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

// Keep only the renderer in the shared runtime. Each lazy chart module
// registers the exact series and components it needs, so opening a line chart
// no longer downloads candlestick, heatmap, and bar implementations as well.
echarts.use([CanvasRenderer]);

export const CHART_GROUP = "quant-charts";

let _connected = false;

export function connectCharts() {
  if (!_connected) {
    echarts.connect(CHART_GROUP);
    _connected = true;
  }
}

export { echarts };
