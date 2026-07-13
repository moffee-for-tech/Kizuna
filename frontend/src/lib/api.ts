const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(): Record<string, string> {
  return { "Content-Type": "application/json" };
}

// All requests include cookies for httpOnly auth
const fetchOpts: RequestInit = { credentials: "include" };

// --- Sessions ---

export async function getSessions() {
  const res = await fetch(`${API_URL}/api/sessions`, { headers: authHeaders(), ...fetchOpts });
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSession(id: string) {
  const res = await fetch(`${API_URL}/api/sessions/${id}`, { headers: authHeaders(), ...fetchOpts });
  if (!res.ok) throw new Error("Failed to fetch session");
  return res.json();
}

export async function createSession(title?: string) {
  const res = await fetch(`${API_URL}/api/sessions`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ title: title || "New Chat" }),
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function deleteSession(id: string) {
  const res = await fetch(`${API_URL}/api/sessions/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Failed to delete session");
  return res.json();
}

// --- Chat ---

export async function sendMessage(message: string, sessionId?: string, documentContext?: string, documentName?: string): Promise<{
  session_id: string;
  message: string;
  structured: StructuredResponse;
  department: string;
}> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ message, session_id: sessionId, document_context: documentContext, document_name: documentName }),
    ...fetchOpts,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Chat failed");
  }
  return res.json();
}

export interface StructuredSection {
  heading: string;
  content: string;
}

export interface ToolCall {
  name: string;
  raw_name: string;
  status: "running" | "success" | "failed";
}

export interface StructuredResponse {
  title: string;
  summary: string;
  sections: StructuredSection[];
  key_takeaways: string[];
  tool_calls?: ToolCall[];
}

export function streamMessage(message: string, sessionId?: string, documentContext?: string, documentName?: string, signal?: AbortSignal) {
  return fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, document_context: documentContext, document_name: documentName }),
    signal,
    ...fetchOpts,
  });
}

// --- Permission confirmation ---

export interface PendingActionField {
  label: string;
  value: string;
  arg_key: string;
  multiline?: boolean;
  editable?: boolean;
}

export interface PendingActionDetail {
  tool_slug: string;
  fields: PendingActionField[];
}

export interface PendingAction {
  action_id: string;
  tool_slug: string;
  human_description: string;
  destructive_subtools: Array<{ tool_slug: string; arguments: Record<string, unknown> }>;
  details: PendingActionDetail[];
  expires_at: string;
}

export async function confirmAction(
  actionId: string,
  approved: boolean,
  overrides?: Record<string, unknown>,
): Promise<{
  session_id: string;
  structured: StructuredResponse;
}> {
  const res = await fetch(`${API_URL}/api/chat/confirm/${encodeURIComponent(actionId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, overrides }),
    ...fetchOpts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Confirm failed: ${res.status} ${text}`);
  }
  return res.json();
}

// --- Templates ---

export async function getPromptTemplates() {
  const res = await fetch(`${API_URL}/api/sessions/templates/prompts`, {
    headers: authHeaders(),
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Failed to fetch templates");
  return res.json();
}

// --- Connectors ---

export async function getConnectors() {
  const res = await fetch(`${API_URL}/api/connectors`, { headers: authHeaders(), ...fetchOpts });
  if (!res.ok) throw new Error("Failed to fetch connectors");
  return res.json();
}

export async function getConnectorAuthUrl(toolkitId: string) {
  const res = await fetch(`${API_URL}/api/connectors/${toolkitId}/auth`, {
    method: "POST",
    headers: authHeaders(),
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Failed to get auth URL");
  return res.json();
}

export async function getConnectorStatus(toolkitId: string) {
  const res = await fetch(`${API_URL}/api/connectors/${toolkitId}/status`, { headers: authHeaders(), ...fetchOpts });
  if (!res.ok) throw new Error("Failed to check status");
  return res.json();
}

export async function disconnectConnector(toolkitId: string) {
  const res = await fetch(`${API_URL}/api/connectors/${toolkitId}/disconnect`, {
    method: "POST",
    headers: authHeaders(),
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Failed to disconnect");
  return res.json();
}

// --- Upload ---

export async function uploadFile(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/upload`, {
    method: "POST",
    body: formData,
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Upload failed");
  return res.json();
}

// --- Auth ---

export async function logoutApi() {
  const res = await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    headers: authHeaders(),
    ...fetchOpts,
  });
  if (!res.ok) throw new Error("Logout failed");
  return res.json();
}

// --- 2FA ---

export interface TwoFactorStatus {
  enabled: boolean;
  enabled_at: string | null;
  backup_codes_remaining: number;
}

export interface TwoFactorSetupPayload {
  secret: string;
  qr_code_png_b64: string;
  backup_codes: string[];
}

async function _jsonOrThrow(res: Response, fallback: string) {
  if (!res.ok) {
    let detail = fallback;
    try {
      const err = await res.json();
      if (err?.detail) detail = err.detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export async function getTwoFactorStatus(): Promise<TwoFactorStatus> {
  const res = await fetch(`${API_URL}/api/auth/2fa/status`, { headers: authHeaders(), ...fetchOpts });
  return _jsonOrThrow(res, "Failed to load 2FA status");
}

export async function setupTwoFactor(): Promise<TwoFactorSetupPayload> {
  const res = await fetch(`${API_URL}/api/auth/2fa/setup`, {
    method: "POST",
    headers: authHeaders(),
    ...fetchOpts,
  });
  return _jsonOrThrow(res, "Failed to start 2FA setup");
}

export async function verifyTwoFactor(code: string) {
  const res = await fetch(`${API_URL}/api/auth/2fa/verify`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ code }),
    ...fetchOpts,
  });
  return _jsonOrThrow(res, "Verification failed");
}

export async function disableTwoFactor(password: string, code: string) {
  const res = await fetch(`${API_URL}/api/auth/2fa/disable`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ password, code }),
    ...fetchOpts,
  });
  return _jsonOrThrow(res, "Failed to disable 2FA");
}

export async function regenerateBackupCodes(password: string, code: string): Promise<{ backup_codes: string[] }> {
  const res = await fetch(`${API_URL}/api/auth/2fa/backup-codes/regenerate`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ password, code }),
    ...fetchOpts,
  });
  return _jsonOrThrow(res, "Failed to regenerate codes");
}
