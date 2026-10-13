// Compatibility shim for builds created before the Newma naming correction.
export * from "./newmaHandoff";
export {
  NEWMA_HANDOFF_PROTOCOL as NUMA_HANDOFF_PROTOCOL,
  buildNewmaHandoffUrl as buildNumaHandoffUrl,
  readNewmaHandoffPayload as readNumaHandoffPayload,
  resolveNewmaAgentUrl as resolveNumaAgentUrl,
} from "./newmaHandoff";
export type { NewmaHandoffPayload as NumaHandoffPayload } from "./newmaHandoff";
