// 공유 API 래퍼 — 모든 도메인 화면은 이 get/post 만 사용한다 (fetch 직접 호출 금지).
// 백엔드 응답 규약: 성공 {ok:true, data, meta?} / 실패 {ok:false, error}.
// 인증(AUTH_ENABLED) 시 토큰을 자동 부착하고 401 이면 /login 으로 보낸다.

// 런타임 override (선택): NEXT_PUBLIC_API_BASE_STORAGE_KEY 를 지정한 앱은
// 그 localStorage 키의 값이 env 보다 우선한다 (설정 화면에서 API 주소 변경 용도).
// SSR/프리렌더에선 window 가 없어 env 폴백을 그대로 사용.
function readApiBaseOverride(): string | null {
  const key = process.env.NEXT_PUBLIC_API_BASE_STORAGE_KEY;
  if (!key || typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // 프라이버시 모드 등 localStorage 접근 예외 대비
  }
}

export const API_BASE = (
  readApiBaseOverride() ||
  process.env.NEXT_PUBLIC_API_BASE ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:5000"
).replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ── 인증 세션 (localStorage) ──

export function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
}

export function getRole(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem("auth_role") : null;
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export async function login(username: string, password: string) {
  const r = await post<{ ok: boolean; data: { token: string; username: string; role: string } }>(
    "/api/auth/login",
    { username, password },
  );
  localStorage.setItem("auth_token", r.data.token);
  localStorage.setItem("auth_user", r.data.username);
  localStorage.setItem("auth_role", r.data.role);
  return r.data;
}

export function logout() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
  localStorage.removeItem("auth_role");
  if (typeof window !== "undefined") window.location.href = "/login";
}

// ── 요청 ──

export function buildUrl(path: string, params?: Record<string, unknown>): string {
  const base = path.startsWith("http") ? path : `${API_BASE}${path}`;
  if (!params) return base;
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") sp.append(k, String(v));
  });
  const q = sp.toString();
  return q ? `${base}?${q}` : base;
}

// EventSource 는 헤더를 못 실으므로 SSE 는 토큰을 쿼리로 부착한다
export function sseUrl(path: string): string {
  const t = getToken();
  return buildUrl(path, t ? { token: t } : undefined);
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("auth_token");
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
    throw new ApiError("인증 필요", 401);
  }
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    /* 비 JSON */
  }
  // ok 필드 없이 {error} 만 주는 legacy 응답도 실패로 판정 (ok:false 규약의 상위집합)
  if (!res.ok || (body && (body.ok === false || (body.error && body.ok === undefined)))) {
    throw new ApiError((body && body.error) || `요청 실패 (HTTP ${res.status})`, res.status);
  }
  return body as T;
}

export async function get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const res = await fetch(buildUrl(path, params), { cache: "no-store", headers: authHeaders() });
  return handle<T>(res);
}

export async function post<T>(path: string, data?: unknown): Promise<T> {
  const res = await fetch(buildUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  return handle<T>(res);
}
