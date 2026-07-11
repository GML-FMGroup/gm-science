import type { SendMessageInput } from "../../app/src/types";

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
