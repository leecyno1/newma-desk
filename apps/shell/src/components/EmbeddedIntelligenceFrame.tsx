import "@newma-desk/desk-ui/mod-theme.css";
import { GlobalIntelligenceApp } from "@newma-desk/global-intelligence";
import type { ModHostConnection } from "@newma-desk/mod-sdk";
import "../../../../modules/global-intelligence/src/styles.css";

export default function EmbeddedIntelligenceFrame({
  hostConnection,
}: {
  hostConnection: Extract<ModHostConnection, { embedded: true }>;
}) {
  return (
    <GlobalIntelligenceApp
      hostConnection={hostConnection}
      gatewayBaseUrl={window.location.origin}
      embedded
    />
  );
}
