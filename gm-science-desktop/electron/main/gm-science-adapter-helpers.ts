import type { CreateGmScienceProjectInput, SendMessageInput } from "../../app/src/types";

export const DEFAULT_GM_SCIENCE_CLIENT_API_PORT = 8876;

export function resolveClientApiPort(env: NodeJS.ProcessEnv = process.env): number {
  const configured = Number(env.OPENPPX_CLIENT_API_PORT?.trim());
  if (Number.isInteger(configured) && configured > 0 && configured <= 65_535) {
    return configured;
  }
  return DEFAULT_GM_SCIENCE_CLIENT_API_PORT;
}

export function isOpenPpxClientApiHealthPayload(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const body = payload as { ok?: unknown; data?: unknown };
  if (body.ok !== true || !body.data || typeof body.data !== "object") {
    return false;
  }
  return (body.data as { service?: unknown }).service === "openppx-client-api";
}

export function formatClientApiStartupError(stderr: string, stdout: string): string {
  const detail = stderr.trim() || stdout.trim() || "The process did not become healthy before the startup timeout.";
  return `Local gm-science client-api failed to start: ${detail}`;
}

export function appendClientApiLogTail(current: string, chunk: string, maxLength = 16_384): string {
  return `${current}${chunk}`.slice(-Math.max(1, maxLength));
}

export function managedProcessAfterClose<T>(current: T | null, closed: T): T | null {
  return current === closed ? null : current;
}

export async function createRunAndOpenEventStream<TStream>(
  createRun: () => Promise<{ runId: string }>,
  openEventStream: (runId: string) => Promise<TStream>,
): Promise<{ runId: string; stream: TStream }> {
  const { runId } = await createRun();
  const stream = await openEventStream(runId);
  return { runId, stream };
}

export function resolveGmScienceDataRoot(
  env: NodeJS.ProcessEnv = process.env,
  homeDir: string = process.env.HOME ?? ".",
): string {
  const configured = env.GM_SCIENCE_DATA_DIR?.trim() || env.OPENPPX_DATA_DIR?.trim();
  if (configured) {
    return configured;
  }
  return `${homeDir.replace(/\/+$/, "")}/.gm-science`;
}

export function buildClientApiSpawnEnv(
  dataRoot: string,
  baseEnv: NodeJS.ProcessEnv = process.env,
): NodeJS.ProcessEnv {
  return {
    ...baseEnv,
    GM_SCIENCE_MODE: "1",
    GM_SCIENCE_DATA_DIR: dataRoot,
    OPENPPX_DATA_DIR: dataRoot,
  };
}

export function buildClientApiRunPath(input: SendMessageInput): string {
  const sessionId = encodeURIComponent(input.sessionId);
  const projectId = input.projectId?.trim();
  if (projectId) {
    return `/api/v1/gm-science/projects/${encodeURIComponent(projectId)}/sessions/${sessionId}/runs`;
  }
  return `/api/v1/agents/${encodeURIComponent(input.agentId)}/sessions/${sessionId}/runs`;
}

export function buildClientApiRunPayload(input: SendMessageInput): Record<string, unknown> {
  if (input.resourceRefs?.length && !input.projectId?.trim()) {
    throw new Error("Project resource references require a Project-scoped run.");
  }
  return {
    text: input.text,
    agent_id: input.agentId,
    ...(input.resourceRefs?.length
      ? {
          resource_refs: input.resourceRefs.map((resource) => ({
            id: resource.id,
            version_or_hash: resource.versionOrHash,
          })),
        }
      : {}),
  };
}

export function buildCreateGmScienceProjectPayload(
  input: CreateGmScienceProjectInput,
): Record<string, unknown> {
  return {
    name: input.name,
    description: input.description ?? "",
    agent_context: input.agentContext ?? "",
    ...(input.enabledSkills !== undefined ? { enabled_skills: input.enabledSkills } : {}),
    ...(input.enabledConnectors !== undefined ? { enabled_connectors: input.enabledConnectors } : {}),
    ...(input.enabledSpecialists !== undefined ? { enabled_specialists: input.enabledSpecialists } : {}),
  };
}
