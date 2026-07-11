import type { MessagePart } from "../types";

type StepPart = Extract<MessagePart, { type: "step_ref" }>;

export function mergeAssistantParts(stepParts: StepPart[], text: string): MessagePart[] {
  const parts: MessagePart[] = [...stepParts];
  if (text.trim()) {
    parts.push({ type: "markdown", text });
  }
  if (parts.length) {
    return parts;
  }
  return [
    {
      type: "step_ref",
      stepId: `step-${crypto.randomUUID()}`,
      title: "Waiting for assistant output",
      status: "running",
      detail: "The client-api is running, but no renderable event has arrived yet.",
    },
  ];
}
