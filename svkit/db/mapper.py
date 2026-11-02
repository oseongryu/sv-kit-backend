"""XML SQL 매퍼 — MyBatis 형태의 선언을 읽어 SQL 과 바인드 파라미터를 만든다.

계약:
  · `SqlMapper(paths)` 는 파일 여럿을 한 레지스트리로 담고 `<mapper namespace>` 가
    이름공간이다. 조회는 `build("<ns>.<id>", params) -> (sql, binds)`.
  · `#{name}` 은 바인드다 — SQLAlchemy `text()` 의 `:name` 으로 나가고 값은 binds 에 실린다.
    `${name}` 은 치환이라 **식별자 모양(`^\\w+(\\.\\w+)*$`)만** 통과한다.
  · `test` 표현식은 파이썬 부분집합이다 — 비교·논리·in·None(`null`)만. 호출·속성·구독은
    파싱 단계에서 거부한다.
  · 파일이 바뀌면 다음 호출에서 다시 읽는다(mtime).
"""
from __future__ import annotations

import ast
import re
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from svkit.infra.logger import get_logger

log = get_logger(__name__)

STATEMENT_TAGS = ("select", "insert", "update", "delete")

_BIND_RE = re.compile(r"#\{\s*(\w+)\s*\}")
_SUBST_RE = re.compile(r"\$\{\s*(\w+)\s*\}")
_IDENT_RE = re.compile(r"^\w+(\.\w+)*$")
_NULL_RE = re.compile(r"\bnull\b")

_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Name, ast.Constant,
    ast.And, ast.Or, ast.Not, ast.Load,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.List, ast.Tuple,
)


class MapperError(RuntimeError):
    """선언이 계약을 어겼다 — 없는 id, 알 수 없는 태그, 거부된 표현식."""


def _text_of(node: Optional[str]) -> str:
    return node or ""


class _Ctx:
    """렌더 한 번의 값·바인드 상태. `resolve` 는 (바인드 키, 값) 을 돌려준다."""

    def __init__(self, params: Mapping[str, Any]) -> None:
        self.vars: dict[str, Any] = dict(params or {})
        self.binds: dict[str, Any] = {}
        self._alias: dict[str, str] = {}
        self._seq = 0

    def value(self, name: str) -> Any:
        return self.vars.get(name)

    def bind(self, name: str) -> str:
        key = self._alias.get(name, name)
        self.binds[key] = self.vars.get(name)
        return key

    def push_item(self, name: str, value: Any) -> tuple:
        """foreach 항목을 넣고 되돌릴 상태를 준다 — 바인드 키는 항목마다 유일하다."""
        prev = (name in self.vars, self.vars.get(name),
                name in self._alias, self._alias.get(name))
        self._seq += 1
        self.vars[name] = value
        self._alias[name] = f"{name}__{self._seq}"
        return prev

    def pop_item(self, name: str, prev: tuple) -> None:
        had_var, val, had_alias, alias = prev
        if had_var:
            self.vars[name] = val
        else:
            self.vars.pop(name, None)
        if had_alias:
            self._alias[name] = alias
        else:
            self._alias.pop(name, None)


def _check_expr(tree: ast.AST, src: str) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise MapperError(
                f"test 표현식에 허용되지 않는 문법이 있다: {src!r} ({type(node).__name__})")


def eval_test(src: str, ctx: _Ctx) -> bool:
    """`test` 한 줄을 판정한다. 이름은 params 에서 오고 없으면 None 이다."""
    expr = _NULL_RE.sub("None", src or "")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise MapperError(f"test 표현식을 읽을 수 없다: {src!r}") from exc
    _check_expr(tree, src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    scope = {n: ctx.value(n) for n in names}
    return bool(eval(compile(tree, "<test>", "eval"), {"__builtins__": {}}, scope))


class _Fragment:
    """`<sql>` 조각 또는 문장 하나 — 렌더는 이 노드 아래를 훑는다."""

    def __init__(self, node: ET.Element, namespace: str) -> None:
        self.node = node
        self.namespace = namespace


class SqlMapper:
    """XML 선언 레지스트리. 파일 목록을 받고 `<ns>.<id>` 로 문장을 만든다."""

    def __init__(self, paths: Iterable[Path | str] | Callable[[], Iterable[Path | str]],
                 ) -> None:
        #: 목록은 호출 시점에 푼다 — 켜진 모듈이 확정되기 전에 굳히면 뒤늦게 로드된
        #: 모듈의 선언이 통째로 빠진다.
        self._source = paths
        self._lock = threading.Lock()
        self._stamp: dict[Path, float] = {}
        self._loaded = False
        self._statements: dict[str, _Fragment] = {}
        self._sql: dict[str, _Fragment] = {}

    # ── 로딩

    def paths(self) -> list[Path]:
        src = self._source
        return [Path(p) for p in (src() if callable(src) else src)]

    def _load_if_stale(self) -> None:
        with self._lock:
            paths = self.paths()
            stamp = {}
            for path in paths:
                try:
                    stamp[path] = path.stat().st_mtime
                except OSError as exc:
                    raise MapperError(f"매퍼 파일을 읽을 수 없다: {path}") from exc
            if self._loaded and stamp == self._stamp:
                return
            statements: dict[str, _Fragment] = {}
            sql: dict[str, _Fragment] = {}
            for path in paths:
                self._read(path, statements, sql)
            self._statements, self._sql, self._stamp = statements, sql, stamp
            self._loaded = True
            log.info("매퍼 로드 문장 %d 조각 %d", len(statements), len(sql))

    def _read(self, path: Path, statements: dict, sql: dict) -> None:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise MapperError(f"매퍼 XML 파싱 실패: {path} — {exc}") from exc
        if root.tag != "mapper":
            raise MapperError(f"루트는 <mapper> 여야 한다: {path} (지금 <{root.tag}>)")
        ns = (root.get("namespace") or "").strip()
        if not ns:
            raise MapperError(f"<mapper> 에 namespace 가 없다: {path}")
        for node in root:
            if node.tag is ET.Comment:
                continue
            qid = (node.get("id") or "").strip()
            if not qid:
                raise MapperError(f"<{node.tag}> 에 id 가 없다: {path}")
            key = f"{ns}.{qid}"
            target = sql if node.tag == "sql" else statements
            if node.tag != "sql" and node.tag not in STATEMENT_TAGS:
                raise MapperError(
                    f"알 수 없는 최상위 태그 <{node.tag}>: {path} "
                    f"(sql·{'·'.join(STATEMENT_TAGS)} 뿐)")
            if key in target:
                raise MapperError(f"id 가 겹친다: {key} ({path})")
            target[key] = _Fragment(node, ns)

    # ── 공개 면

    def ids(self) -> list[str]:
        self._load_if_stale()
        return sorted(self._statements)

    def sql_ids(self) -> list[str]:
        self._load_if_stale()
        return sorted(self._sql)

    def build(self, qid: str, params: Optional[Mapping[str, Any]] = None,
              ) -> tuple[str, dict[str, Any]]:
        """선언 하나를 SQL 과 바인드로 만든다. 없는 id 는 MapperError."""
        self._load_if_stale()
        frag = self._statements.get(qid)
        if frag is None:
            raise MapperError(f"그런 쿼리가 없다: {qid}")
        return self._render(frag, params)

    def build_fragment(self, refid: str, params: Optional[Mapping[str, Any]] = None,
                       ) -> tuple[str, dict[str, Any]]:
        """`<sql>` 조각 하나를 따로 렌더한다 — 아직 파이썬이 조립하는 문장이 같은
        조건 선언을 쓰게 하는 통로다(조건의 자리를 둘로 만들지 않는다)."""
        self._load_if_stale()
        frag = self._sql.get(refid)
        if frag is None:
            raise MapperError(f"그런 <sql> 조각이 없다: {refid}")
        return self._render(frag, params)

    def _render(self, frag: _Fragment, params: Optional[Mapping[str, Any]],
                ) -> tuple[str, dict[str, Any]]:
        ctx = _Ctx(params or {})
        out: list[str] = []
        self._render_children(frag.node, frag.namespace, ctx, out)
        return _tidy("".join(out)), ctx.binds

    # ── 렌더

    def _render_children(self, node: ET.Element, ns: str, ctx: _Ctx,
                         out: list[str]) -> None:
        out.append(self._text(node.text, ctx))
        for child in node:
            if child.tag is not ET.Comment:
                self._render_tag(child, ns, ctx, out)
            out.append(self._text(child.tail, ctx))

    def _render_tag(self, node: ET.Element, ns: str, ctx: _Ctx,
                    out: list[str]) -> None:
        tag = node.tag
        if tag == "if":
            if eval_test(node.get("test", ""), ctx):
                self._render_children(node, ns, ctx, out)
        elif tag == "choose":
            self._render_choose(node, ns, ctx, out)
        elif tag == "where":
            self._render_trim(node, ns, ctx, out,
                              prefix="WHERE", prefix_overrides="AND |OR ")
        elif tag == "set":
            self._render_trim(node, ns, ctx, out,
                              prefix="SET", suffix_overrides=",")
        elif tag == "trim":
            self._render_trim(
                node, ns, ctx, out,
                prefix=node.get("prefix", ""), suffix=node.get("suffix", ""),
                prefix_overrides=node.get("prefixOverrides", ""),
                suffix_overrides=node.get("suffixOverrides", ""))
        elif tag == "foreach":
            self._render_foreach(node, ns, ctx, out)
        elif tag == "include":
            self._render_include(node, ns, ctx, out)
        else:
            raise MapperError(f"알 수 없는 태그 <{tag}>")

    def _render_choose(self, node: ET.Element, ns: str, ctx: _Ctx,
                       out: list[str]) -> None:
        otherwise = None
        for child in node:
            if child.tag is ET.Comment:
                continue
            if child.tag == "when":
                if eval_test(child.get("test", ""), ctx):
                    self._render_children(child, ns, ctx, out)
                    return
            elif child.tag == "otherwise":
                otherwise = child
            else:
                raise MapperError(f"<choose> 안에는 when·otherwise 뿐이다 (<{child.tag}>)")
        if otherwise is not None:
            self._render_children(otherwise, ns, ctx, out)

    def _render_trim(self, node: ET.Element, ns: str, ctx: _Ctx, out: list[str], *,
                     prefix: str = "", suffix: str = "",
                     prefix_overrides: str = "", suffix_overrides: str = "") -> None:
        inner: list[str] = []
        self._render_children(node, ns, ctx, inner)
        body = "".join(inner).strip()
        if not body:
            return
        for token in (t for t in prefix_overrides.split("|") if t):
            if body[:len(token)].upper() == token.upper():
                body = body[len(token):].lstrip()
                break
        for token in (t for t in suffix_overrides.split("|") if t):
            if body[-len(token):].upper() == token.upper():
                body = body[:-len(token)].rstrip()
                break
        out.append(" " + " ".join(p for p in (prefix, body, suffix) if p) + " ")

    def _render_foreach(self, node: ET.Element, ns: str, ctx: _Ctx,
                        out: list[str]) -> None:
        coll_name = node.get("collection", "")
        item = node.get("item", "item")
        index = node.get("index") or ""
        values = ctx.value(coll_name)
        if values is None:
            values = []
        if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
            raise MapperError(f"<foreach collection={coll_name!r}> 이 목록이 아니다")
        # MyBatis 와 같이 Mapping 은 (키, 값) 을 돈다 — `index` 가 위치가 아니라 **키**다.
        # 목록에서는 위치 그대로다.
        if isinstance(values, Mapping):
            pairs = list(values.items())
        else:
            pairs = list(enumerate(values))
        if not pairs:
            return
        parts: list[str] = []
        for i, value in pairs:
            prev = ctx.push_item(item, value)
            prev_idx = ctx.push_item(index, i) if index else None
            piece: list[str] = []
            self._render_children(node, ns, ctx, piece)
            parts.append("".join(piece).strip())
            if index:
                ctx.pop_item(index, prev_idx)
            ctx.pop_item(item, prev)
        sep = node.get("separator", "")
        out.append(node.get("open", "") + sep.join(parts) + node.get("close", ""))

    def _render_include(self, node: ET.Element, ns: str, ctx: _Ctx,
                        out: list[str]) -> None:
        ref = (node.get("refid") or "").strip()
        if not ref:
            raise MapperError("<include> 에 refid 가 없다")
        key = ref if "." in ref else f"{ns}.{ref}"
        frag = self._sql.get(key)
        if frag is None:
            raise MapperError(f"그런 <sql> 조각이 없다: {key}")
        # MyBatis 와 같이 <property> 가 include 지점마다 값을 준다 — 한 문장이 같은
        # 조각을 다른 식으로 여럿 끼울 때 쓴다. 값은 이 include 를 렌더하는 동안만 산다.
        props: dict[str, str] = {}
        for child in node:
            if child.tag != "property":
                raise MapperError(f"<include> 의 자식은 <property> 뿐이다: <{child.tag}>")
            name, value = child.get("name"), child.get("value")
            if not name or value is None:
                raise MapperError("<property> 에는 name 과 value 가 다 있어야 한다")
            props[name] = value
        saved = {k: (k in ctx.vars, ctx.vars.get(k)) for k in props}
        ctx.vars.update(props)
        try:
            self._render_children(frag.node, frag.namespace, ctx, out)
        finally:
            for k, (had, val) in saved.items():
                if had:
                    ctx.vars[k] = val
                else:
                    ctx.vars.pop(k, None)

    # ── 텍스트

    def _text(self, raw: Optional[str], ctx: _Ctx) -> str:
        text = _text_of(raw)
        if not text:
            return ""
        text = _BIND_RE.sub(lambda m: ":" + ctx.bind(m.group(1)), text)
        return _SUBST_RE.sub(lambda m: _substitute(m.group(1), ctx), text)


def _substitute(name: str, ctx: _Ctx) -> str:
    """`${}` 는 식별자만 통과한다 — 값이 SQL 조각이면 그 자리는 태그로 적어야 한다."""
    value = ctx.value(name)
    if value is None:
        raise MapperError(f"${{{name}}} 에 줄 값이 없다")
    text = str(value)
    if not _IDENT_RE.match(text):
        raise MapperError(f"${{{name}}} 은 식별자만 받는다 (받은 값: {text!r})")
    return text


def _tidy(sql: str) -> str:
    """빈 줄·꼬리 공백만 정리한다 — 줄바꿈은 로그·EXPLAIN 가독성이라 남긴다."""
    lines = [line.rstrip() for line in sql.splitlines()]
    return "\n".join(line for line in lines if line.strip()).strip()
