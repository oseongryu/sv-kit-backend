// 주입형 전송 코어 — 멀티서버 앱(소스 해석이 런타임에 바뀌는 앱)용.
// "어디로 보낼지"(resolve)와 "실패를 어떻게 알릴지"(events)를 앱이 주입하고,
// 요청/오류판정/raw fetch/SSE 파싱은 이 코어가 담당한다.
// 단일 서버 앱은 api.ts(get/post)로 충분 — 이 코어는 그 상위 호환 계층.

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ResolvedSource {
  baseUrl: string;
  token: string | null;
  label: string;
}

export interface HttpErrorInfo {
  method: HttpMethod;
  url: string;
  status: number;
  statusText: string;
  message: string; // 응답 body 의 {error} 또는 텍스트
}

export interface NetworkErrorInfo {
  method: HttpMethod;
  url: string;
  error: unknown;
}

// 알림 정책 주입 지점 — 기본은 console 로그만. toast 등 UX 는 앱이 얹는다.
export interface TransportEvents {
  onSkip?: (info: { method: string; path: string; label: string }) => void;
  onHttpError?: (info: HttpErrorInfo) => void;
  onNetworkError?: (info: NetworkErrorInfo) => void;
}

export interface EventStreamHandlers {
  onMessage: (text: string) => void;
  onOpen?: () => void;
  onError?: (err: Error) => void;
}

export interface EventStreamHandle {
  close: () => void;
}

export interface Transport {
  g: <T>(path: string) => Promise<T | null>;
  p: <T>(path: string, body?: unknown) => Promise<T>;
  put: <T>(path: string, body?: unknown) => Promise<T>;
  patch: <T>(path: string, body?: unknown) => Promise<T>;
  del: <T>(path: string, body?: unknown) => Promise<T>;
  raw: (method: HttpMethod, path: string, init?: RequestInit) => Promise<Response>;
  baseUrl: () => string;
  buildUrl: (path: string) => string;
  authHeaders: () => Record<string, string>;
  sourceLabel: () => string;
  openEventStream: (path: string, handlers: EventStreamHandlers) => EventStreamHandle;
}

async function readErrorMessage(res: Response): Promise<string> {
  try {
    const bodyText = await res.text();
    if (!bodyText) return "";
    try {
      const parsed = JSON.parse(bodyText);
      return typeof parsed?.error === "string" ? parsed.error : bodyText;
    } catch {
      return bodyText;
    }
  } catch {
    return ""; // body 읽기 실패 — 무시
  }
}

export function makeTransport(
  resolve: () => ResolvedSource,
  events: TransportEvents = {},
): Transport {
  async function request<T>(
    method: HttpMethod,
    path: string,
    body?: unknown,
  ): Promise<T | null> {
    const { baseUrl, token, label } = resolve();
    const tag = `[API ${label}]`;
    if (!baseUrl) {
      console.warn(`${tag} ${method} ${path} → SKIP (baseUrl 미해결)`);
      events.onSkip?.({ method, path, label });
      return null;
    }
    const url = `${baseUrl}${path}`;
    console.debug(`${tag} ${method} ${url}`);
    try {
      const headers: Record<string, string> = {};
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(url, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const message = await readErrorMessage(res);
        console.error(
          `${tag} ${method} ${url} → ${res.status} ${res.statusText}` +
            (message ? `\n  ${message}` : ""),
        );
        events.onHttpError?.({
          method, url, status: res.status, statusText: res.statusText, message,
        });
        return null;
      }
      if (res.status === 204) return null as unknown as T;
      return (await res.json()) as T;
    } catch (e) {
      console.error(`${tag} ${method} ${url} 실패`, e);
      events.onNetworkError?.({ method, url, error: e });
      return null;
    }
  }

  // null 을 흘려보내는 g 와 달리, 쓰기 계열은 호출부 타입 편의상 T 로 단언한다
  async function requestStrict<T>(
    method: HttpMethod,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const v = await request<T>(method, path, body);
    return v as T;
  }

  async function rawFetch(
    method: HttpMethod,
    path: string,
    init?: RequestInit,
  ): Promise<Response> {
    const { baseUrl, token, label } = resolve();
    const tag = `[API ${label}]`;
    if (!baseUrl) {
      console.warn(`${tag} ${method} ${path} → SKIP raw (baseUrl 미해결)`);
      throw new Error(`API baseUrl unresolved for ${label}`);
    }
    const url = `${baseUrl}${path}`;
    console.debug(`${tag} ${method} ${url} (raw)`);
    const headers: Record<string, string> = {
      ...((init?.headers as Record<string, string>) ?? {}),
    };
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(url, { ...init, method, headers });
  }

  // 네이티브 EventSource 는 커스텀 헤더를 못 실으므로 fetch + ReadableStream 으로
  // SSE 를 직접 파싱 — 표준 Authorization 헤더로 인증 가능
  function openEventStream(
    path: string,
    handlers: EventStreamHandlers,
  ): EventStreamHandle {
    const { baseUrl, token, label } = resolve();
    const tag = `[API ${label}]`;
    const ctrl = new AbortController();
    if (!baseUrl) {
      console.warn(`${tag} STREAM ${path} → SKIP (baseUrl 미해결)`);
      events.onSkip?.({ method: "STREAM", path, label });
      queueMicrotask(() => handlers.onError?.(new Error("baseUrl unresolved")));
      return { close: () => ctrl.abort() };
    }
    const url = `${baseUrl}${path}`;
    console.debug(`${tag} STREAM ${url}`);

    const reqHeaders: Record<string, string> = { Accept: "text/event-stream" };
    if (token) reqHeaders.Authorization = `Bearer ${token}`;

    (async () => {
      try {
        const res = await fetch(url, { headers: reqHeaders, signal: ctrl.signal });
        if (!res.ok || !res.body) {
          console.warn(`${tag} STREAM ${url} → ${res.status} ${res.statusText}`);
          handlers.onError?.(new Error(`HTTP ${res.status}`));
          return;
        }
        handlers.onOpen?.();
        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buf = "";
        const SEP = /\r?\n\r?\n/g;
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          SEP.lastIndex = 0;
          let m: RegExpExecArray | null;
          let consumed = 0;
          while ((m = SEP.exec(buf)) !== null) {
            const event = buf.slice(consumed, m.index);
            consumed = m.index + m[0].length;
            const dataLines: string[] = [];
            for (const rawLine of event.split(/\r?\n/)) {
              if (!rawLine || rawLine.startsWith(":")) continue;
              if (rawLine.startsWith("data:")) {
                const v = rawLine.slice(5);
                dataLines.push(v.startsWith(" ") ? v.slice(1) : v);
              }
            }
            if (dataLines.length > 0) handlers.onMessage(dataLines.join("\n"));
          }
          if (consumed > 0) buf = buf.slice(consumed);
        }
      } catch (err) {
        if ((err as { name?: string })?.name === "AbortError") return;
        console.error(`${tag} STREAM ${url} 실패`, err);
        handlers.onError?.(err instanceof Error ? err : new Error(String(err)));
      }
    })();

    return { close: () => ctrl.abort() };
  }

  return {
    g: <T>(path: string) => request<T>("GET", path),
    p: <T>(path: string, body?: unknown) => requestStrict<T>("POST", path, body),
    put: <T>(path: string, body?: unknown) => requestStrict<T>("PUT", path, body),
    patch: <T>(path: string, body?: unknown) => requestStrict<T>("PATCH", path, body),
    del: <T>(path: string, body?: unknown) => requestStrict<T>("DELETE", path, body),
    raw: rawFetch,
    baseUrl: () => resolve().baseUrl,
    buildUrl: (path: string) => `${resolve().baseUrl}${path}`,
    authHeaders: (): Record<string, string> => {
      const { token } = resolve();
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
    sourceLabel: () => resolve().label,
    openEventStream,
  };
}
