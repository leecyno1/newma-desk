import type { PickingInfo } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import type {
  GlobalIntelCategory,
  GlobalIntelPoint,
  GlobalIntelRoute,
} from "./data";

export type IntelligenceMapMode = "signals" | "heat";

export interface IntelligenceRegion {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface IntelligenceWatchRegion {
  id: string;
  name: string;
  bounds: IntelligenceRegion;
  alertCount: number;
}

export interface IntelligenceMapFocus {
  id: string;
  longitude: number;
  latitude: number;
  label: string;
  zoom?: number;
}

interface IntelligenceCluster {
  id: string;
  longitude: number;
  latitude: number;
  points: GlobalIntelPoint[];
  primary: GlobalIntelPoint;
}

const COUNTRY_SOURCE = "global-intelligence-countries";
const COUNTRY_LAYER = "global-intelligence-country-risk";
const COUNTRY_GEOJSON = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json";

const CATEGORY_COLOR: Record<GlobalIntelCategory, [number, number, number]> = {
  market: [64, 198, 255],
  news: [154, 139, 255],
  policy: [245, 190, 74],
  conflict: [255, 74, 101],
  disaster: [255, 129, 70],
  military: [190, 103, 255],
  infrastructure: [55, 214, 161],
  maritime: [41, 201, 210],
  climate: [139, 210, 79],
  health: [255, 111, 177],
  cyber: [45, 212, 255],
  nuclear: [255, 228, 94],
  aviation: [98, 168, 255],
  space: [245, 215, 110],
  technology: [177, 140, 255],
  society: [255, 159, 138],
  prediction: [115, 214, 165],
};

const SEVERITY_WEIGHT = {
  critical: 1,
  high: 0.78,
  medium: 0.5,
  low: 0.28,
  info: 0.16,
} as const;

const ROUTE_COLOR: Record<GlobalIntelRoute["kind"], [number, number, number]> = {
  pipeline: [245, 190, 74],
  cable: [64, 198, 255],
  shipping: [55, 214, 161],
  flight: [98, 168, 255],
};

type RouteRenderSegment = {
  route: GlobalIntelRoute;
  path: Array<[number, number]>;
};

const ROUTE_DASH_PATTERN: Record<GlobalIntelRoute["kind"], [number, number]> = {
  pipeline: [4.6, 2.8],
  cable: [2.8, 3.4],
  shipping: [3.8, 3.6],
  flight: [2.2, 3.2],
};

function routeColor(
  route: GlobalIntelRoute,
  theme: "light" | "dark",
  alpha: number,
): [number, number, number, number] {
  if (["destroyed", "cancelled", "terminated"].includes(route.status ?? "")) {
    return theme === "dark" ? [255, 74, 101, alpha] : [184, 37, 62, alpha];
  }
  if ((route.riskScore ?? 0) >= 70) {
    return theme === "dark" ? [255, 74, 101, alpha] : [184, 37, 62, alpha];
  }
  if ((route.riskScore ?? 0) >= 45) {
    return theme === "dark" ? [255, 145, 74, alpha] : [200, 86, 35, alpha];
  }
  if ((route.riskScore ?? 0) > 0) {
    return theme === "dark" ? [245, 190, 74, alpha] : [168, 112, 20, alpha];
  }
  const [red, green, blue] = ROUTE_COLOR[route.kind];
  return theme === "dark"
    ? [red, green, blue, alpha]
    : [Math.round(red * 0.72), Math.round(green * 0.72), Math.round(blue * 0.72), alpha];
}

function wrappedLongitudeDelta(start: number, end: number) {
  return ((end - start + 540) % 360) - 180;
}

function visualRoutePath(route: GlobalIntelRoute): Array<[number, number]> {
  if (route.kind === "pipeline" || route.path.length < 2) return route.path;
  const seed = [...route.id].reduce((sum, character) => sum + character.charCodeAt(0), 0);
  return route.path.slice(0, -1).flatMap((start, segmentIndex) => {
    const end = route.path[segmentIndex + 1]!;
    const longitudeDelta = wrappedLongitudeDelta(start[0], end[0]);
    const latitudeDelta = end[1] - start[1];
    const direction = (seed + segmentIndex) % 2 ? 1 : -1;
    const maxBend = route.kind === "shipping" ? 5.5 : 8;
    const bend = direction * Math.min(maxBend, Math.max(0.8, Math.abs(longitudeDelta) * 0.035));
    const steps = Math.max(8, Math.min(28, Math.ceil(Math.abs(longitudeDelta) / 5)));
    return Array.from({ length: steps }, (_, step): [number, number] => {
      const progress = step / steps;
      return [
        start[0] + longitudeDelta * progress,
        Math.max(-82, Math.min(82, start[1] + latitudeDelta * progress + Math.sin(Math.PI * progress) * bend)),
      ];
    });
  }).concat([route.path.at(-1)!]);
}

function dashedRouteSegments(route: GlobalIntelRoute): RouteRenderSegment[] {
  const path = route.path;
  const [dashLength, gapLength] = ROUTE_DASH_PATTERN[route.kind];
  const pattern = [dashLength, gapLength];
  const segments: RouteRenderSegment[] = [];
  let patternIndex = 0;
  let patternOffset = 0;
  let drawing = true;
  let current: Array<[number, number]> = [];

  const flush = () => {
    if (current.length > 1) segments.push({ route, path: current });
    current = [];
  };

  for (let index = 0; index < path.length - 1; index += 1) {
    const start = path[index]!;
    const end = path[index + 1]!;
    const longitudeDelta = wrappedLongitudeDelta(start[0], end[0]);
    const latitudeDelta = end[1] - start[1];
    const latitudeScale = Math.cos(((start[1] + end[1]) / 2) * Math.PI / 180);
    const length = Math.hypot(longitudeDelta * latitudeScale, latitudeDelta);
    if (length < 0.001) continue;
    let consumed = 0;
    while (consumed < length - 0.0001) {
      const available = pattern[patternIndex]! - patternOffset;
      const taken = Math.min(available, length - consumed);
      const fromProgress = consumed / length;
      const toProgress = (consumed + taken) / length;
      const from: [number, number] = [start[0] + longitudeDelta * fromProgress, start[1] + latitudeDelta * fromProgress];
      const to: [number, number] = [start[0] + longitudeDelta * toProgress, start[1] + latitudeDelta * toProgress];
      if (drawing) {
        if (!current.length) current.push(from);
        current.push(to);
      } else if (current.length) {
        flush();
      }
      consumed += taken;
      patternOffset += taken;
      if (patternOffset >= pattern[patternIndex]! - 0.0001) {
        patternOffset = 0;
        patternIndex = (patternIndex + 1) % pattern.length;
        drawing = !drawing;
        if (!drawing) flush();
      }
    }
  }
  flush();
  return segments;
}

function mapStyle(theme: "light" | "dark") {
  const style = theme === "dark" ? "dark_all" : "light_all";
  const riskColors = theme === "dark"
    ? [
        0, "rgba(0,0,0,0)",
        20, "rgba(245,190,74,0.10)",
        50, "rgba(255,129,70,0.22)",
        100, "rgba(255,74,101,0.38)",
      ]
    : [
        0, "rgba(255,255,255,0)",
        20, "rgba(205,142,21,0.10)",
        50, "rgba(219,91,37,0.18)",
        100, "rgba(184,37,62,0.28)",
      ];
  return {
    version: 8 as const,
    sources: {
      carto: {
        type: "raster" as const,
        tiles: [
          `https://a.basemaps.cartocdn.com/${style}/{z}/{x}/{y}@2x.png`,
          `https://b.basemaps.cartocdn.com/${style}/{z}/{x}/{y}@2x.png`,
          `https://c.basemaps.cartocdn.com/${style}/{z}/{x}/{y}@2x.png`,
          `https://d.basemaps.cartocdn.com/${style}/{z}/{x}/{y}@2x.png`,
        ],
        tileSize: 256,
        attribution: "© OpenStreetMap © CARTO",
      },
      [COUNTRY_SOURCE]: {
        type: "geojson" as const,
        data: COUNTRY_GEOJSON,
      },
    },
    layers: [
      { id: "carto-basemap", type: "raster" as const, source: "carto" },
      {
        id: COUNTRY_LAYER,
        type: "fill" as const,
        source: COUNTRY_SOURCE,
        paint: {
          "fill-color": [
            "interpolate", ["linear"], ["coalesce", ["feature-state", "risk"], 0],
            ...riskColors,
          ],
          "fill-outline-color": theme === "dark" ? "rgba(245,190,74,0.16)" : "rgba(142,80,30,0.18)",
        },
      },
    ],
  } as maplibregl.StyleSpecification;
}

function pointColor(point: GlobalIntelPoint): [number, number, number, number] {
  const [red, green, blue] = CATEGORY_COLOR[point.category];
  return [red, green, blue, point.severity === "info" ? 155 : 225];
}

function pointRadius(point: GlobalIntelPoint) {
  return point.severity === "critical"
    ? 7
    : point.severity === "high"
      ? 5.7
      : point.severity === "medium"
        ? 4.4
        : 3.4;
}

const SEVERITY_ORDER = { critical: 5, high: 4, medium: 3, low: 2, info: 1 } as const;

function clusterPoints(points: GlobalIntelPoint[], zoom: number): IntelligenceCluster[] {
  const cellSize = zoom >= 5 ? 0 : Math.max(0.45, 28 / 2 ** Math.max(0, zoom - 1));
  if (!cellSize) {
    return points.map((point) => ({
      id: point.id,
      longitude: point.longitude,
      latitude: point.latitude,
      points: [point],
      primary: point,
    }));
  }
  const buckets = new Map<string, GlobalIntelPoint[]>();
  for (const point of points) {
    const key = `${Math.floor((point.longitude + 180) / cellSize)}:${Math.floor((point.latitude + 90) / cellSize)}`;
    buckets.set(key, [...(buckets.get(key) ?? []), point]);
  }
  return [...buckets.entries()].map(([key, members]) => {
    const primary = [...members].sort((left, right) => SEVERITY_ORDER[right.severity] - SEVERITY_ORDER[left.severity])[0]!;
    return {
      id: `cluster-${key}`,
      longitude: members.reduce((sum, point) => sum + point.longitude, 0) / members.length,
      latitude: members.reduce((sum, point) => sum + point.latitude, 0) / members.length,
      points: members,
      primary,
    };
  });
}

export function IntelligenceMap({
  points,
  selectedPointId,
  theme,
  mode,
  routes,
  showRoutes,
  showCountryRisk,
  countryRisk,
  selectedRegion,
  focusLocation,
  watchedRegions,
  onSelect,
  onRouteSelect,
  onRegionSelect,
}: {
  points: GlobalIntelPoint[];
  selectedPointId?: string;
  theme: "light" | "dark";
  mode: IntelligenceMapMode;
  routes: GlobalIntelRoute[];
  showRoutes: boolean;
  showCountryRisk: boolean;
  countryRisk: Record<string, number>;
  selectedRegion?: IntelligenceRegion;
  focusLocation?: IntelligenceMapFocus;
  watchedRegions: IntelligenceWatchRegion[];
  onSelect(point: GlobalIntelPoint): void;
  onRouteSelect(route: GlobalIntelRoute): void;
  onRegionSelect(region: IntelligenceRegion): void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | undefined>(undefined);
  const overlayRef = useRef<MapboxOverlay | undefined>(undefined);
  const mapThemeRef = useRef(theme);
  const onSelectRef = useRef(onSelect);
  const onRouteSelectRef = useRef(onRouteSelect);
  const onRegionSelectRef = useRef(onRegionSelect);
  const [zoom, setZoom] = useState(1.45);
  const [hovered, setHovered] = useState<{
    title: string;
    detail: string;
    meta: string;
    x: number;
    y: number;
  }>();

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);
  useEffect(() => { onRouteSelectRef.current = onRouteSelect; }, [onRouteSelect]);
  useEffect(() => { onRegionSelectRef.current = onRegionSelect; }, [onRegionSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: mapStyle(theme),
      center: [12, 23],
      zoom: 1.45,
      minZoom: 1,
      maxZoom: 12,
      attributionControl: false,
      renderWorldCopies: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "bottom-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
    map.addControl(overlay);
    const handleZoom = () => setZoom(map.getZoom());
    const handleBoxZoom = () => {
      requestAnimationFrame(() => {
        const bounds = map.getBounds();
        onRegionSelectRef.current({
          west: bounds.getWest(),
          south: bounds.getSouth(),
          east: bounds.getEast(),
          north: bounds.getNorth(),
        });
      });
    };
    map.on("zoomend", handleZoom);
    map.on("boxzoomend", handleBoxZoom);
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      map.off("zoomend", handleZoom);
      map.off("boxzoomend", handleBoxZoom);
      overlay.finalize();
      map.remove();
      overlayRef.current = undefined;
      mapRef.current = undefined;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || mapThemeRef.current === theme) return;
    mapThemeRef.current = theme;
    if (map.isStyleLoaded()) map.setStyle(mapStyle(theme));
    else map.once("load", () => map.setStyle(mapStyle(theme)));
  }, [theme]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (!map.getSource(COUNTRY_SOURCE)) return;
      for (const [countryCode, risk] of Object.entries(countryRisk)) {
        map.setFeatureState({ source: COUNTRY_SOURCE, id: countryCode }, { risk });
      }
      if (map.getLayer(COUNTRY_LAYER)) {
        map.setLayoutProperty(COUNTRY_LAYER, "visibility", showCountryRisk ? "visible" : "none");
      }
    };
    map.on("styledata", apply);
    map.on("sourcedata", apply);
    apply();
    return () => {
      map.off("styledata", apply);
      map.off("sourcedata", apply);
    };
  }, [countryRisk, showCountryRisk, theme]);

  const clusters = useMemo(() => clusterPoints(points, zoom), [points, zoom]);
  const displayRoutes = useMemo(
    () => routes.map((route) => ({ ...route, path: visualRoutePath(route) })),
    [routes],
  );
  const routeSegments = useMemo(
    () => displayRoutes.flatMap((route) => dashedRouteSegments(route)),
    [displayRoutes],
  );
  const routeEndpoints = useMemo(() => displayRoutes.flatMap((route) => {
    const start = route.path[0];
    const end = route.path.at(-1);
    if (!start || !end) return [];
    return [
      { id: `${route.id}-start`, route, position: start },
      { id: `${route.id}-end`, route, position: end },
    ];
  }), [displayRoutes]);

  const layers = useMemo(() => {
    const heatOuter = new ScatterplotLayer<IntelligenceCluster>({
      id: "global-intelligence-heat-outer",
      data: clusters,
      visible: mode === "heat",
      stroked: false,
      filled: true,
      radiusUnits: "pixels",
      getPosition: (cluster) => [cluster.longitude, cluster.latitude],
      getRadius: (cluster) => Math.min(82, 24 + Math.sqrt(cluster.points.length) * 9),
      getFillColor: (cluster) => {
        const [red, green, blue] = CATEGORY_COLOR[cluster.primary.category];
        return [red, green, blue, Math.round(24 + SEVERITY_WEIGHT[cluster.primary.severity] * 34)];
      },
    });
    const heatInner = new ScatterplotLayer<IntelligenceCluster>({
      id: "global-intelligence-heat-inner",
      data: clusters,
      visible: mode === "heat",
      stroked: false,
      filled: true,
      radiusUnits: "pixels",
      getPosition: (cluster) => [cluster.longitude, cluster.latitude],
      getRadius: (cluster) => Math.min(42, 10 + Math.sqrt(cluster.points.length) * 4.5),
      getFillColor: (cluster) => {
        const [red, green, blue] = CATEGORY_COLOR[cluster.primary.category];
        return [red, green, blue, Math.round(42 + SEVERITY_WEIGHT[cluster.primary.severity] * 82)];
      },
    });
    const routeHalo = new PathLayer<RouteRenderSegment>({
      id: "global-intelligence-route-halo",
      data: routeSegments,
      visible: showRoutes,
      widthUnits: "pixels",
      widthMinPixels: 1,
      widthMaxPixels: 3,
      wrapLongitude: true,
      jointRounded: true,
      capRounded: true,
      getPath: (segment) => segment.path,
      getWidth: (segment) => segment.route.kind === "pipeline" ? 2.8 : 2.2,
      getColor: (segment) => routeColor(segment.route, theme, (segment.route.riskScore ?? 0) > 0 ? 48 : 10),
    });
    const routeLayer = new PathLayer<RouteRenderSegment>({
      id: "global-intelligence-routes",
      data: routeSegments,
      visible: showRoutes,
      pickable: true,
      widthUnits: "pixels",
      widthMinPixels: 0.7,
      widthMaxPixels: 2.2,
      wrapLongitude: true,
      jointRounded: true,
      capRounded: true,
      getPath: (segment) => segment.path,
      getWidth: (segment) => (segment.route.riskScore ?? 0) >= 70
        ? 1.8
        : (segment.route.riskScore ?? 0) >= 45
          ? 1.45
          : segment.route.kind === "pipeline" ? 1.05 : 0.85,
      getColor: (segment) => routeColor(segment.route, theme, (segment.route.riskScore ?? 0) > 0 ? 225 : theme === "dark" ? 100 : 112),
      onHover: (info: PickingInfo<RouteRenderSegment>) => {
        const route = info.object?.route;
        setHovered(route ? {
          title: route.name,
          detail: route.detail,
          meta: `${route.kind.toUpperCase()} · ${route.pathType === "corridor" ? "示意走廊" : "精确线路"} · 风险 ${route.riskScore ?? 0}`,
          x: info.x,
          y: info.y,
        } : undefined);
      },
      onClick: (info: PickingInfo<RouteRenderSegment>) => {
        if (info.object) onRouteSelectRef.current(info.object.route);
      },
    });
    const routeEndpointLayer = new ScatterplotLayer<(typeof routeEndpoints)[number]>({
      id: "global-intelligence-route-endpoints",
      data: routeEndpoints,
      visible: showRoutes,
      stroked: true,
      filled: true,
      radiusUnits: "pixels",
      wrapLongitude: true,
      radiusMinPixels: 2,
      getPosition: (endpoint) => endpoint.position,
      getRadius: 2.4,
      getFillColor: (endpoint) => routeColor(endpoint.route, theme, (endpoint.route.riskScore ?? 0) > 0 ? 210 : 105),
      getLineColor: theme === "dark" ? [4, 17, 16, 220] : [255, 255, 255, 235],
      getLineWidth: 1,
    });
    const signals = new ScatterplotLayer<IntelligenceCluster>({
      id: "global-intelligence-signals",
      data: clusters,
      opacity: mode === "heat" ? 0.34 : 1,
      pickable: true,
      autoHighlight: true,
      stroked: true,
      filled: true,
      radiusUnits: "pixels",
      radiusMinPixels: 2.5,
      radiusMaxPixels: 14,
      lineWidthUnits: "pixels",
      getPosition: (cluster) => [cluster.longitude, cluster.latitude],
      getRadius: (cluster) => Math.min(18, pointRadius(cluster.primary) + Math.sqrt(cluster.points.length) * 2.2),
      getFillColor: (cluster) => pointColor(cluster.primary),
      getLineColor: (cluster) => cluster.points.some((point) => point.id === selectedPointId)
        ? theme === "dark" ? [255, 255, 255, 255] : [16, 45, 36, 255]
        : theme === "dark" ? [4, 17, 16, 210] : [246, 249, 245, 230],
      getLineWidth: (cluster) => cluster.points.some((point) => point.id === selectedPointId) ? 2 : 0.8,
      transitions: {
        getRadius: 180,
        getFillColor: 180,
      },
      onClick: (info: PickingInfo<IntelligenceCluster>) => {
        if (!info.object) return;
        if (info.object.points.length === 1) {
          onSelectRef.current(info.object.primary);
          return;
        }
        mapRef.current?.easeTo({
          center: [info.object.longitude, info.object.latitude],
          zoom: Math.min(8, zoom + 2),
          duration: 420,
        });
      },
      onHover: (info: PickingInfo<IntelligenceCluster>) => {
        setHovered(info.object ? {
          title: info.object.points.length > 1 ? `${info.object.points.length} 个聚合信号` : info.object.primary.title,
          detail: info.object.points.length > 1 ? info.object.points.slice(0, 3).map((point) => point.title).join(" · ") : info.object.primary.detail,
          meta: `${info.object.primary.category} · ${info.object.primary.severity}`,
          x: info.x,
          y: info.y,
        } : undefined);
      },
    });
    const clusterLabels = new TextLayer<IntelligenceCluster>({
      id: "global-intelligence-cluster-labels",
      data: clusters.filter((cluster) => cluster.points.length > 1),
      visible: mode === "signals",
      getPosition: (cluster) => [cluster.longitude, cluster.latitude],
      getText: (cluster) => String(cluster.points.length),
      getColor: theme === "dark" ? [255, 255, 255, 235] : [16, 45, 36, 245],
      getSize: 11,
      sizeUnits: "pixels",
      fontWeight: 700,
    });
    const watchedRegionLayer = new PathLayer<IntelligenceWatchRegion>({
      id: "global-intelligence-watch-regions",
      data: watchedRegions,
      widthUnits: "pixels",
      getWidth: (region) => region.alertCount > 0 ? 2.2 : 1.2,
      getColor: (region) => region.alertCount > 0
        ? theme === "dark" ? [255, 74, 101, 235] : [184, 37, 62, 235]
        : theme === "dark" ? [245, 190, 74, 205] : [151, 101, 8, 220],
      getPath: ({ bounds }) => [
        [bounds.west, bounds.south], [bounds.east, bounds.south],
        [bounds.east, bounds.north], [bounds.west, bounds.north],
        [bounds.west, bounds.south],
      ],
    });
    const watchedRegionLabels = new TextLayer<IntelligenceWatchRegion>({
      id: "global-intelligence-watch-region-labels",
      data: watchedRegions,
      getPosition: ({ bounds }) => [bounds.west, bounds.north],
      getText: (region) => `${region.name}${region.alertCount ? ` · ${region.alertCount} NEW` : ""}`,
      getColor: (region) => region.alertCount > 0
        ? theme === "dark" ? [255, 116, 135, 255] : [153, 27, 48, 255]
        : theme === "dark" ? [245, 190, 74, 245] : [117, 76, 2, 245],
      getSize: 10,
      sizeUnits: "pixels",
      getPixelOffset: [5, -7],
      getTextAnchor: "start",
      fontWeight: 700,
    });
    const regionPath = selectedRegion ? new PathLayer<IntelligenceRegion>({
      id: "global-intelligence-selected-region",
      data: [selectedRegion],
      widthUnits: "pixels",
      getWidth: 2,
      getColor: [55, 214, 161, 230],
      getPath: (region) => [
        [region.west, region.south], [region.east, region.south],
        [region.east, region.north], [region.west, region.north],
        [region.west, region.south],
      ],
    }) : null;
    const focusRing = focusLocation ? new ScatterplotLayer<IntelligenceMapFocus>({
      id: "global-intelligence-focus-ring",
      data: [focusLocation],
      getPosition: (focus) => [focus.longitude, focus.latitude],
      radiusUnits: "pixels",
      getRadius: 22,
      filled: false,
      stroked: true,
      getLineColor: theme === "dark" ? [245, 190, 74, 255] : [142, 88, 0, 255],
      getLineWidth: 2,
      lineWidthUnits: "pixels",
    }) : null;
    const focusLabel = focusLocation ? new TextLayer<IntelligenceMapFocus>({
      id: "global-intelligence-focus-label",
      data: [focusLocation],
      getPosition: (focus) => [focus.longitude, focus.latitude],
      getText: (focus) => focus.label,
      getColor: theme === "dark" ? [245, 210, 132, 255] : [105, 66, 0, 255],
      getSize: 10,
      sizeUnits: "pixels",
      getPixelOffset: [0, -30],
      getTextAnchor: "middle",
      fontWeight: 700,
    }) : null;
    return [
      heatOuter,
      heatInner,
      routeHalo,
      routeLayer,
      routeEndpointLayer,
      watchedRegionLayer,
      watchedRegionLabels,
      signals,
      clusterLabels,
      ...(regionPath ? [regionPath] : []),
      ...(focusRing ? [focusRing] : []),
      ...(focusLabel ? [focusLabel] : []),
    ];
  }, [clusters, focusLocation, mode, routeEndpoints, routeSegments, selectedPointId, selectedRegion, showRoutes, theme, watchedRegions]);

  useEffect(() => {
    overlayRef.current?.setProps({ layers });
  }, [layers]);

  useEffect(() => {
    const point = points.find((item) => item.id === selectedPointId);
    if (!point) return;
    mapRef.current?.easeTo({
      center: [point.longitude, point.latitude],
      zoom: Math.max(mapRef.current.getZoom(), 4.2),
      duration: 520,
    });
  }, [points, selectedPointId]);

  useEffect(() => {
    if (!focusLocation) return;
    mapRef.current?.easeTo({
      center: [focusLocation.longitude, focusLocation.latitude],
      zoom: focusLocation.zoom ?? 4.2,
      duration: 620,
    });
  }, [focusLocation]);

  return (
    <div className="intel-map-shell">
      <div ref={containerRef} className="intel-map-canvas" aria-label="全球情报地图" />
      {hovered ? (
        <div
          className="intel-map-tooltip"
          style={{ transform: `translate(${hovered.x + 14}px, ${hovered.y + 14}px)` }}
        >
          <small>{hovered.meta}</small>
          <strong>{hovered.title}</strong>
          <span>{hovered.detail}</span>
        </div>
      ) : null}
      <div className="intel-map-signature">
        <i />MAPLIBRE GL
        <i />DECK.GL
      </div>
      {showRoutes ? (
        <div className="intel-route-legend" aria-label="战略通道图例">
          {(["pipeline", "cable", "shipping", "flight"] as const).map((kind) => {
            const count = routes.filter((route) => route.kind === kind).length;
            if (!count) return null;
            return (
              <span key={kind} style={{ "--route-color": `rgb(${ROUTE_COLOR[kind].join(" ")})` } as CSSProperties}>
                <i />{kind === "pipeline" ? "能源" : kind === "cable" ? "光缆" : kind === "shipping" ? "航运 / 油运" : "航空"} {count}
              </span>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
