import { useMemo } from "react";

import "@newma-desk/desk-ui/mod-theme.css";
import {
  MarketTerminalApp,
  MarketWorkspaceApp,
  createMarketDataSource,
  marketWorkspaceFromSearch,
} from "@newma-desk/market-daily";
import type { ModBridge, ModHostConnection } from "@newma-desk/mod-sdk";
import "../../../../modules/market-daily/src/styles.css";
import "../../../../modules/market-daily/src/workspaces/workspaces.css";

interface EmbeddedMarketFrameProps {
  search: string;
  hostConnection: Extract<ModHostConnection, { embedded: true }>;
  bridge?: ModBridge;
}

export default function EmbeddedMarketFrame({
  search,
  hostConnection,
  bridge,
}: EmbeddedMarketFrameProps) {
  const workspace = useMemo(() => marketWorkspaceFromSearch(search), [search]);
  const dataSource = useMemo(
    () => createMarketDataSource({
      baseUrl: window.location.origin,
      fetch: window.fetch.bind(window),
      invokeAction: hostConnection.invokeAction,
    }),
    [hostConnection],
  );

  return workspace ? (
    <MarketWorkspaceApp
      config={workspace}
      hostConnection={hostConnection}
      bridge={bridge}
      dataSource={dataSource}
      embedded
    />
  ) : (
    <MarketTerminalApp
      hostConnection={hostConnection}
      bridge={bridge}
      dataSource={dataSource}
      embedded
    />
  );
}
