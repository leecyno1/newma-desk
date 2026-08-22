import "@newma-desk/desk-ui/mod-theme.css";
import { GlobalIntelligenceApp } from "@newma-desk/global-intelligence";
import type { ModHostConnection } from "@newma-desk/mod-sdk";
import "../../../../modules/global-intelligence/src/styles.css";

export default function EmbeddedIntelligenceFrame({
  hostConnection,
  search,
}: {
  hostConnection: Extract<ModHostConnection, { embedded: true }>;
  search?: string;
}) {
  const topicId = new URLSearchParams(search).get("topic") as "fed-rates" | "hormuz" | "us-china-trade" | null;
  return (
    <GlobalIntelligenceApp
      hostConnection={hostConnection}
      gatewayBaseUrl={window.location.origin}
      embedded
      topicId={topicId ?? undefined}
    />
  );
}
