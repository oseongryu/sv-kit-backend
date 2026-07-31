// 공유 훅 — 화면 상태 유지/디바운스/실시간 스트림. 도메인 화면이 공통 사용.
import { useEffect, useState } from "react";

// localStorage 연동 상태 훅(필터/설정 등 화면 상태 유지)
export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    const saved = localStorage.getItem(key);
    if (saved !== null) {
      try {
        setValue(JSON.parse(saved));
      } catch {}
    }
  }, [key]);
  const set = (v: T) => {
    setValue(v);
    localStorage.setItem(key, JSON.stringify(v));
  };
  return [value, set];
}

// 디바운스 값 훅(검색 입력 등)
export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// SSE 스트림 훅. 연결 시 data 갱신, 끊기면 connected=false(호출측에서 폴링 폴백)
export function useEventStream<T>(url: string): { data: T | null; connected: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!url || typeof window === "undefined" || typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    try {
      es = new EventSource(url);
      es.onopen = () => setConnected(true);
      es.onmessage = (e) => {
        try {
          setData(JSON.parse(e.data));
        } catch {}
      };
      es.onerror = () => setConnected(false);
    } catch {
      setConnected(false);
    }
    return () => {
      if (es) es.close();
    };
  }, [url]);
  return { data, connected };
}
