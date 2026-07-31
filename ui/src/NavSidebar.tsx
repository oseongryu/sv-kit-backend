"use client";
// /api/domains 를 읽어 등록된 도메인 네비를 자동 구성한다.
// 도메인이 늘어나도 shell 은 그대로 — 링크만 추가된다.
// 앱 고유 값(타이틀·추가 링크)은 props 로 주입한다 — 패키지는 앱 설정을 모른다.
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { get, getToken, logout } from "./api";

export interface NavLink {
  href: string;
  label: string;
}

interface Domain {
  slug: string;
  title: string;
  prefix: string | null;
}

export function NavSidebar({
  title,
  extraLinks = [],
}: {
  title: string;
  extraLinks?: NavLink[];
}) {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [token, setToken] = useState<string | null>(null);
  const pathname = usePathname();
  useEffect(() => {
    get<{ ok: boolean; data: Domain[] }>("/api/domains")
      .then((r) => setDomains(r.data || []))
      .catch(() => setDomains([]));
  }, []);
  useEffect(() => {
    setToken(getToken());
  }, [pathname]);

  const linkStyle = (href: string) => ({
    padding: "6px 8px",
    borderRadius: 6,
    color: pathname === href ? "var(--text)" : "var(--muted)",
    background: pathname === href ? "var(--border)" : "transparent",
  });

  return (
    <nav
      style={{
        width: 220,
        borderRight: "1px solid var(--border)",
        padding: 16,
        background: "var(--panel)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Link href="/" style={{ fontWeight: 700, fontSize: 18 }}>
        {title}
      </Link>
      <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 4 }}>
        {domains.map((d) => (
          <Link key={d.slug} href={`/${d.slug}`} style={linkStyle(`/${d.slug}`)}>
            {d.title}
          </Link>
        ))}
        {extraLinks.map((l) => (
          <Link key={l.href} href={l.href} style={linkStyle(l.href)}>
            {l.label}
          </Link>
        ))}
        {domains.length === 0 && extraLinks.length === 0 && (
          <span style={{ color: "var(--muted)", fontSize: 13 }}>도메인 없음</span>
        )}
      </div>
      {token && (
        <button
          onClick={logout}
          style={{
            marginTop: "auto",
            padding: "6px 8px",
            borderRadius: 6,
            border: "1px solid var(--border)",
            background: "transparent",
            color: "var(--muted)",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          로그아웃
        </button>
      )}
    </nav>
  );
}
