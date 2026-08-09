export type ModCopilotMode = "ask" | "edit";

export type ModCopilotPromptIntent =
  | "summary"
  | "evidence"
  | "risk"
  | "scenario"
  | "extension"
  | "next-step"
  | "modification"
  | "validation";

export interface ModCopilotPromptSuggestion {
  id: string;
  intent: ModCopilotPromptIntent;
  label: string;
  prompt: string;
}

export interface ModCopilotPromptGroup {
  id: string;
  label: string;
  suggestions: ModCopilotPromptSuggestion[];
}

export type ModCopilotPrompts = Record<ModCopilotMode, ModCopilotPromptGroup[]>;

const INTENTS = new Set<ModCopilotPromptIntent>([
  "summary",
  "evidence",
  "risk",
  "scenario",
  "extension",
  "next-step",
  "modification",
  "validation",
]);

function boundedText(value: unknown, maxLength: number): string {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

function promptGroups(value: unknown): ModCopilotPromptGroup[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 8).flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object") return [];
    const row = candidate as Record<string, unknown>;
    const id = boundedText(row.id, 64);
    const label = boundedText(row.label, 80);
    if (!id || !label || !Array.isArray(row.suggestions)) return [];
    const suggestions = row.suggestions.slice(0, 8).flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const suggestion = item as Record<string, unknown>;
      const suggestionId = boundedText(suggestion.id, 64);
      const intent = boundedText(suggestion.intent, 32);
      const suggestionLabel = boundedText(suggestion.label, 120);
      const prompt = boundedText(suggestion.prompt, 8_000);
      if (
        !suggestionId ||
        !INTENTS.has(intent as ModCopilotPromptIntent) ||
        !suggestionLabel ||
        !prompt
      ) {
        return [];
      }
      return [
        {
          id: suggestionId,
          intent: intent as ModCopilotPromptIntent,
          label: suggestionLabel,
          prompt,
        },
      ];
    });
    return suggestions.length ? [{ id, label, suggestions }] : [];
  });
}

export function normalizeModCopilotPrompts(value: unknown): ModCopilotPrompts {
  const root =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  return {
    ask: promptGroups(root.ask),
    edit: promptGroups(root.edit),
  };
}
