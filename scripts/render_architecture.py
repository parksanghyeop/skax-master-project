"""cta 아키텍처 그림(docs/architecture.excalidraw)을 생성한다 — 산출물 재생성용.

근거: docs/architecture.md(층 구조·모듈 표), 실제 import 방향, README.md(명령 흐름).
외부 서비스에 아무것도 보내지 않고 Excalidraw JSON을 직접 쓴다.
출력은 excalidraw.com 또는 VS Code Excalidraw 확장에서 연다.

사용:  python scripts/render_architecture.py docs/architecture.excalidraw
"""

# ruff: noqa: E501 — 그림 안 글자 문자열은 줄바꿈 표시 위치가 곧 상자 줄바꿈이라 100자 규칙을 적용하지 않는다
import json
import random
import sys
import time
from pathlib import Path

random.seed(20260912)
NOW = int(time.time() * 1000)
elements: list[dict] = []
_counter = 0


def _id(prefix: str) -> str:
    global _counter
    _counter += 1
    return f"{prefix}{_counter:03d}"


def _base(kind: str, x: float, y: float, w: float, h: float, **kw) -> dict:
    el = {
        "id": kw.pop("id", _id(kind[0])),
        "type": kind,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": None,
        "roundness": None,
        "seed": random.randint(1, 2**31),
        "version": 1,
        "versionNonce": random.randint(1, 2**31),
        "isDeleted": False,
        "boundElements": [],
        "updated": NOW,
        "link": None,
        "locked": False,
    }
    el.update(kw)
    return el


def _text_size(text: str, font: int) -> tuple[float, float]:
    """대략적 글자 폭·높이 — 한글은 정사각형, 영문은 0.6배."""
    lines = text.split("\n")
    widest = 0.0
    for line in lines:
        w = 0.0
        for ch in line:
            w += font * (1.0 if ord(ch) > 0x2E7F else 0.6)
        widest = max(widest, w)
    return widest, font * 1.25 * len(lines)


def text(x, y, s, font=16, align="left", color="#1e1e1e", family=1, frame=None, bold=False):
    w, h = _text_size(s, font)
    el = _base(
        "text",
        x,
        y,
        w,
        h,
        text=s,
        originalText=s,
        fontSize=font,
        fontFamily=family,
        textAlign=align,
        verticalAlign="top",
        containerId=None,
        autoResize=True,
        lineHeight=1.25,
        strokeColor=color,
        frameId=frame,
    )
    elements.append(el)
    return el


def box(
    x,
    y,
    w,
    h,
    label="",
    fill="transparent",
    stroke="#1e1e1e",
    font=14,
    dashed=False,
    frame=None,
    stroke_w=1,
    label_valign="middle",
    rounded=True,
    family=1,
    kind="rectangle",
):
    rect = _base(
        kind,
        x,
        y,
        w,
        h,
        backgroundColor=fill,
        strokeColor=stroke,
        strokeStyle="dashed" if dashed else "solid",
        strokeWidth=stroke_w,
        roundness={"type": 3} if rounded else None,
        frameId=frame,
    )
    elements.append(rect)
    if label:
        tw, th = _text_size(label, font)
        tw = min(tw, w - 10)
        if label_valign == "top":
            ty = y + 8
        else:
            ty = y + (h - th) / 2
        t = _base(
            "text",
            x + (w - tw) / 2,
            ty,
            tw,
            th,
            text=label,
            originalText=label,
            fontSize=font,
            fontFamily=family,
            textAlign="center",
            verticalAlign=label_valign,
            containerId=rect["id"],
            autoResize=True,
            lineHeight=1.25,
            strokeColor="#1e1e1e",
            frameId=frame,
        )
        elements.append(t)
        rect["boundElements"].append({"id": t["id"], "type": "text"})
    return rect


def arrow(
    src,
    dst,
    points=None,
    label="",
    color="#1e1e1e",
    dashed=False,
    frame=None,
    start=None,
    end=None,
    stroke_w=1,
    font=13,
    free=False,
    label_dx=0,
    label_dy=0,
):
    """src/dst 박스를 잇는 화살표. points는 절대 좌표 목록(시작·끝 포함).
    free=True면 라벨을 화살표에 묶지 않고 중간점 위에 자유 텍스트로 놓는다(짧은 화살표용)."""
    if points is None:
        # 기본: 두 박스 중심을 직선으로
        sx, sy = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
        ex, ey = dst["x"] + dst["width"] / 2, dst["y"] + dst["height"] / 2
        points = [(sx, sy), (ex, ey)]
    x0, y0 = points[0]
    rel = [[px - x0, py - y0] for px, py in points]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    el = _base(
        "arrow",
        x0,
        y0,
        max(xs) - min(xs),
        max(ys) - min(ys),
        points=rel,
        lastCommittedPoint=None,
        startBinding=(
            {"elementId": src["id"], "focus": 0, "gap": 4, "fixedPoint": None} if src else None
        ),
        endBinding=(
            {"elementId": dst["id"], "focus": 0, "gap": 4, "fixedPoint": None} if dst else None
        ),
        startArrowhead=start,
        endArrowhead="arrow" if end is None else end,
        elbowed=False,
        strokeColor=color,
        strokeStyle="dashed" if dashed else "solid",
        strokeWidth=stroke_w,
        roundness={"type": 2},
        frameId=frame,
    )
    elements.append(el)
    if src:
        src["boundElements"].append({"id": el["id"], "type": "arrow"})
    if dst:
        dst["boundElements"].append({"id": el["id"], "type": "arrow"})
    if label and free:
        tw, th = _text_size(label, font)
        mid = len(points) // 2
        if len(points) % 2 == 0:
            mx = (points[mid - 1][0] + points[mid][0]) / 2
            my = (points[mid - 1][1] + points[mid][1]) / 2
        else:
            mx, my = points[mid]
        text(
            mx - tw / 2 + label_dx,
            my - th - 6 + label_dy,
            label,
            font=font,
            align="center",
            color=color,
            frame=frame,
        )
        return el
    if label:
        tw, th = _text_size(label, font)
        mid = len(points) // 2
        if len(points) % 2 == 0:
            mx = (points[mid - 1][0] + points[mid][0]) / 2
            my = (points[mid - 1][1] + points[mid][1]) / 2
        else:
            mx, my = points[mid]
        t = _base(
            "text",
            mx - tw / 2,
            my - th / 2,
            tw,
            th,
            text=label,
            originalText=label,
            fontSize=font,
            fontFamily=1,
            textAlign="center",
            verticalAlign="middle",
            containerId=el["id"],
            autoResize=True,
            lineHeight=1.25,
            strokeColor=color,
            frameId=frame,
        )
        elements.append(t)
        el["boundElements"].append({"id": t["id"], "type": "text"})
    return el


def frame(x, y, w, h, name):
    el = _base("frame", x, y, w, h, name=name, roundness=None)
    elements.append(el)
    return el


# ── 색상 (Excalidraw 팔레트) ─────────────────────────────────────────
C = {
    "cli": ("#a5d8ff", "#1971c2"),
    "adapters": ("#ffec99", "#f08c00"),
    "core": ("#b2f2bb", "#2f9e44"),
    "llm": ("#ffc9c9", "#e03131"),
    "graph": ("#d0bfff", "#6741d9"),
    "sandbox": ("#ffd8a8", "#e8590c"),
    "evals": ("#e9ecef", "#868e96"),
    "ext": ("#ffffff", "#495057"),
    "state": ("#fff4e6", "#868e96"),
}


def layer(x, y, w, h, key, title, subtitle="", fr=None):
    fill, stroke = C[key]
    r = box(x, y, w, h, "", fill=fill, stroke=stroke, stroke_w=2, frame=fr)
    r["fillStyle"] = "hachure" if key == "ext" else "solid"
    r["opacity"] = 100
    text(x + 14, y + 10, title, font=20, color=stroke, frame=fr)
    if subtitle:
        text(x + 14, y + 38, subtitle, font=13, color="#495057", frame=fr)
    return r


def module(x, y, w, h, label, key, fr=None, font=13):
    fill, stroke = C[key]
    return box(x, y, w, h, label, fill="#ffffff", stroke=stroke, font=font, frame=fr)


# ═══════════════════════════════════════════════════════════════════
# 프레임 1 — 층 구조와 의존 방향
# ═══════════════════════════════════════════════════════════════════
F1 = frame(0, 0, 2060, 1180, "1. 층 구조와 의존 방향")
f = F1["id"]

text(40, 30, "Code Test Agent (cta) — 아키텍처: 층 구조와 의존 방향", font=30, frame=f)
text(
    40,
    75,
    "실선 화살표 = import 방향(의존). core가 가장 안쪽이라 바깥 층을 모른다(R1). "
    "점선 = 외부 시스템·파일 접근. 근거: docs/architecture.md · tests/test_layering.py · 실제 import",
    font=14,
    color="#495057",
    frame=f,
)

# 사용자
user = box(
    40, 200, 170, 90, "사용자\n(터미널 · CI)", fill="#ffffff", stroke="#495057", font=16, frame=f
)

# ── cli 층 ──
cli = layer(
    300,
    150,
    880,
    215,
    "cli",
    "cli — cta 명령의 조립·입출력만 (판단 로직 없음)",
    "generate / maintain / resolve / diff·apply·discard / graph / eval / demo",
    fr=f,
)
row1 = [
    "main.py\n진입점·서브커맨드",
    "generate.py\n재료→생성→게이트→제안",
    "maintain_cmd.py\n변경 대응 조립·판단 블록",
    "resolve_cmd.py\n사람 결정으로 재개",
    "proposals · escalations\n· memos (.cta/ 보관소)",
]
row2 = [
    "graph_cmd · eval_cmd\n· demo_cmd",
    "graph_access.py\nNeo4j 확인→파싱 폴백",
    "render.py · hints.py\n출력 형식 · 오류 안내",
    "locate.py · file_mode.py\n프로젝트 자동 인식",
    "eval_intents.py\n의도 분류 정확도 측정",
]
bw, bh, gap = 162, 52, 10
for i, s in enumerate(row1):
    module(316 + i * (bw + gap), 218, bw, bh, s, "cli", fr=f, font=12)
for i, s in enumerate(row2):
    module(316 + i * (bw + gap), 218 + bh + 10, bw, bh, s, "cli", fr=f, font=12)

# ── adapters 층 ──
ad = layer(
    300,
    440,
    600,
    300,
    "adapters",
    "adapters/java — 구체 구현 (Java · Maven · JUnit 5)",
    "core 포트(Protocol) 구현 · JaCoCo·PIT 호출. 새 언어 = 폴더 추가. fake.py = 오프라인 Fake",
    fr=f,
)
ad_mods = [
    "maven.py · runner.py\n프로젝트 탐지 · TestRunner",
    "inspector.py · similar.py\n대상 조사 · 유사 테스트",
    "materials.py\n재료 수집(메서드 선정 등)",
    "writer.py · merge.py\n테스트 쓰기(범위 강제)",
    "changes.py\ngit diff→변경 심볼·단서",
    "gates.py ①~④ · mutation.py ⑤\n· regression.py ⑥",
    "coverage.py\nJaCoCo 실측 (COVERS)",
    "graph_builder.py\n소스→노드·엣지",
    "skills/ SKILL.md + select.py\n테스트 작성 스킬 (ADR-0017)",
    "parsing · failures\n· assert_report",
    "quality.py\nassert 수 비교",
    "fake.py\n인메모리 Fake 어댑터",
]
bw2, bh2 = 180, 52
for i, s in enumerate(ad_mods):
    r, c = divmod(i, 3)
    module(316 + c * (bw2 + 10), 512 + r * (bh2 + 8), bw2, bh2, s, "adapters", fr=f, font=12)

# ── evals ──
ev = layer(
    920,
    440,
    260,
    120,
    "evals",
    "evals — 골든 케이스",
    "재현 가능한 검증 시나리오 배선",
    fr=f,
)
module(
    936,
    500,
    228,
    48,
    "golden_case.py · golden/ 카세트\n(adapters·core·llm·sandbox 사용)",
    "evals",
    fr=f,
    font=12,
)

# ── core 층 ──
core = layer(
    300,
    810,
    880,
    330,
    "core",
    "core — 언어 무관 핵심 로직 (가장 안쪽, 바깥 층 import 금지)",
    "R1: java/maven/junit 문자열 금지  ·  R2: 규칙표·게이트에 LLM 없음  ·  R4: 고유 도구 정확히 6개",
    fr=f,
)
core_mods = [
    "ports.py\n포트(Protocol) + 데이터 모델",
    "tools/ 고유 도구 6개 (1도구 1파일)\ninspect_target · query_code_graph · write_test\nrun_tests · check_quality · report_finding",
    "writer_graph.py  [engine=legacy, 기본]\nLangGraph 서브그래프 · 최대 8회 · interrupt",
    "agent/  [engine=deep, ADR-0024]\nbuild · tools · subagents(explorer/writer/\ndiagnoser) · limits · prompts/",
    "submit.py\n생성→게이트 재시도 루프",
    "gates.py\n게이트 실행기 (cta.toml [gates])",
    "pipeline/ decide.py 규칙표(LLM 금지)\n· maintain.py 변경 대응 · models.py",
    "user_gate.py\ninterrupt 사람 개입 (두 엔진 공용)",
    "config.py · textlimit.py\ncta.toml 설정 · 반환 길이 상한",
]
cw = [200, 300, 330, 300, 200, 200, 300, 260, 260]
# 1행: ports, tools, writer_graph  / 2행: agent, submit, gates / 3행: pipeline, user_gate, config
positions = [
    (316, 880, 200, 62),
    (526, 880, 320, 62),
    (856, 880, 308, 62),
    (316, 950, 330, 62),
    (656, 950, 250, 62),
    (916, 950, 248, 62),
    (316, 1020, 330, 62),
    (656, 1020, 250, 62),
    (916, 1020, 248, 62),
]
for s, (x, y, w, h) in zip(core_mods, positions, strict=True):
    module(x, y, w, h, s, "core", fr=f, font=12)

# ── 오른쪽 독립 층: llm / graph / sandbox ──
llm = layer(
    1300,
    150,
    380,
    290,
    "llm",
    "llm — LLM 호출의 유일한 통로 (R7)",
    "record & replay가 작동해야 한다. CI는 재생 모드, 실호출 폴백 없음",
    fr=f,
)
llm_mods = [
    "config.py  make_llm_client()\n.env 로딩 · 클라이언트 생성 유일 입구",
    "gateway.py · chat_model.py\n게이트웨이 실호출 · AzureChatOpenAI",
    "replay.py · model_cassette.py\n카세트 v1 · v2(미들웨어) 녹음/재생",
    "intent.py · generation.py\n의도 분류 · 테스트 코드 생성",
    "metering.py · masking.py · prompts/*.md\n토큰 합산·예산 · 시크릿 가림 · 프롬프트",
]
for i, s in enumerate(llm_mods):
    module(1316, 208 + i * 46, 348, 40, s, "llm", fr=f, font=11)

gr = layer(
    1300,
    480,
    380,
    190,
    "graph",
    "graph — 코드 그래프 (언어를 모른다)",
    "노드 3종(클래스·메서드·테스트) · 엣지 3종(DECLARES·CREATES·COVERS)",
    fr=f,
)
gr_mods = [
    "model.py\n노드·엣지 모델",
    "store.py\nGraphStore + 인메모리",
    "neo4j_store.py\nNeo4j 실물 저장소",
    "answers.py\n질의→답 문장 (CodeGraph)",
]
for i, s in enumerate(gr_mods):
    r, c = divmod(i, 2)
    module(1316 + c * 178, 540 + r * 56, 170, 48, s, "graph", fr=f, font=12)

sb = layer(
    1300,
    710,
    380,
    210,
    "sandbox",
    "sandbox — 실행 장치 (R6)",
    "무엇을 실행하는지 모른다. 빌드 도구 지식은 adapters가 가진다",
    fr=f,
)
sb_mods = [
    "local_sandbox.py [기본]  이 PC의 Maven·JDK (~/.m2)",
    "docker_sandbox.py  --runner docker · 네트워크 차단 · 마운트 통제",
    "factory.py  choose_runner — 명시 없으면 local, 폴백 없음",
]
for i, s in enumerate(sb_mods):
    module(1316, 768 + i * 44, 348, 36, s, "sandbox", fr=f, font=11)


# ── 외부 시스템 ──
def ext(x, y, w, h, label, fr=f):
    r = box(x, y, w, h, label, fill="#f8f9fa", stroke="#495057", font=13, dashed=True, frame=fr)
    return r


gw = ext(1770, 200, 240, 90, "사내 LLM 게이트웨이\n(Azure OpenAI 호환, gpt-5)\n주소·키는 .env로만")
neo = ext(1770, 530, 240, 80, "Neo4j (선택)\n별도 컨테이너 · 없으면\n파싱 폴백")
jdk = ext(1770, 730, 240, 100, "로컬 Maven · JDK 17+\n(~/.m2)  또는\nDocker 컨테이너(격리)")
target = ext(
    40,
    470,
    200,
    130,
    "대상 Maven 프로젝트\n(단일 모듈 · JUnit 5)\ngit 이력 · src/main\n· src/test · pom.xml",
)
state = box(
    40,
    650,
    200,
    120,
    ".cta/ 상태 저장소\nproposals(제안)\nescalations(사람 확인)\nmemos(판단 메모)",
    fill=C["state"][0],
    stroke=C["state"][1],
    font=13,
    dashed=True,
    frame=f,
)
cfg = ext(
    40, 820, 200, 90, "cta.toml (게이트 기준치·\n반복 상한·모델·예산)\n.env (시크릿, gitignore)"
)

# ── 의존 화살표 ──
A = "#1e1e1e"
# 사용자 → cli
arrow(user, cli, [(210, 245), (300, 245)], label="cta <명령>", frame=f, stroke_w=2, free=True)
# cli → adapters, core, evals
arrow(cli, ad, [(600, 365), (600, 440)], frame=f, color=C["cli"][1], stroke_w=2)
arrow(cli, ev, [(1050, 365), (1050, 440)], frame=f, color=C["cli"][1], stroke_w=2)
arrow(
    cli,
    core,
    [(1180, 355), (1205, 355), (1205, 830), (1180, 830)],
    frame=f,
    color=C["cli"][1],
    stroke_w=2,
)
# cli → llm / graph / sandbox
arrow(cli, llm, [(1180, 260), (1300, 260)], frame=f, color=C["cli"][1], stroke_w=2)
arrow(
    cli,
    gr,
    [(1180, 330), (1230, 330), (1230, 560), (1300, 560)],
    frame=f,
    color=C["cli"][1],
    stroke_w=2,
)
arrow(
    cli,
    sb,
    [(1180, 340), (1230, 340), (1230, 790), (1300, 790)],
    frame=f,
    color=C["cli"][1],
    stroke_w=2,
)
# adapters → core / graph / sandbox
arrow(
    ad,
    core,
    [(600, 740), (600, 810)],
    label="포트 구현",
    frame=f,
    color=C["adapters"][1],
    stroke_w=2,
)
arrow(
    ad,
    gr,
    [(900, 610), (1300, 610)],
    label="그래프를 채운다",
    frame=f,
    color=C["adapters"][1],
    stroke_w=2,
)
arrow(
    ad,
    sb,
    [(900, 700), (1100, 700), (1100, 850), (1300, 850)],
    label="명령 실행 위임",
    frame=f,
    color=C["adapters"][1],
    stroke_w=2,
)
# evals → adapters (짧게)
arrow(ev, ad, [(920, 520), (900, 520)], frame=f, color=C["evals"][1])
# llm → core (실제 import: 포트 타입)
arrow(
    llm,
    core,
    [(1340, 440), (1265, 440), (1265, 900), (1180, 900)],
    label="ports 타입만 참조",
    frame=f,
    color=C["llm"][1],
    stroke_w=2,
)
# 외부 시스템 (점선)
arrow(
    llm,
    gw,
    [(1680, 245), (1770, 245)],
    label="HTTPS",
    dashed=True,
    frame=f,
    color="#495057",
    free=True,
)
arrow(
    gr,
    neo,
    [(1680, 570), (1770, 570)],
    label="bolt",
    dashed=True,
    frame=f,
    color="#495057",
    free=True,
)
arrow(
    sb,
    jdk,
    [(1680, 780), (1770, 780)],
    label="mvn test\n(선택 실행만, R5)",
    dashed=True,
    frame=f,
    color="#495057",
    free=True,
    font=11,
    label_dy=36,
)
arrow(
    ad,
    target,
    [(300, 540), (240, 540)],
    label="git diff · 소스 읽기\n테스트 파일 쓰기",
    dashed=True,
    frame=f,
    color="#495057",
    start="arrow",
    free=True,
    font=11,
    label_dy=-24,
)
arrow(
    cli,
    state,
    [(300, 340), (140, 340), (140, 650)],
    label="제안·사람 확인·메모 읽기/쓰기\n(apply 전까지 소스 반영 없음)",
    dashed=True,
    frame=f,
    color="#495057",
    start="arrow",
    free=True,
    font=11,
    label_dy=-14,
)
arrow(
    core,
    cfg,
    [(300, 900), (240, 900)],
    label="config.py",
    dashed=True,
    frame=f,
    color="#495057",
    free=True,
    font=11,
)

# 범례
lg_y = 1150
text(40, 1150 - 1150 + 1000, "", font=1, frame=f)  # 자리 유지용 아님 — 제거 가능
legend_x = 1300
text(legend_x, 950, "읽는 법", font=16, frame=f)
text(
    legend_x,
    975,
    "· 실선 = import 방향 (A → B: A가 B를 안다)\n"
    "· 점선 = 프로세스·파일 시스템 경계 밖 접근\n"
    "· LLM이 있는 곳은 llm/ 층 하나뿐 — 규칙표·게이트·제안·재개는 전부 일반 코드\n"
    "· 작성 엔진은 둘이 공존(legacy 기본 · deep). 게이트 루프는 둘을 같은 계약으로 부른다\n"
    "· 단위 테스트 236건 — tests/test_layering.py가 import 방향과 금지 문자열을 검사",
    font=13,
    color="#495057",
    frame=f,
)

# ═══════════════════════════════════════════════════════════════════
# 프레임 2 — 명령별 실행 흐름
# ═══════════════════════════════════════════════════════════════════
F2 = frame(0, 1260, 2060, 900, "2. 명령별 실행 흐름")
f2 = F2["id"]
Y0 = 1260
text(
    40,
    Y0 + 30,
    "명령별 실행 흐름 — LLM은 두 곳(의도 판단·테스트 작성)에만, 안전장치는 전부 일반 코드",
    font=30,
    frame=f2,
)
text(
    40,
    Y0 + 75,
    "종료 코드: 0 정상 · 3 사람 확인 필요(실패 아님) · 2 품질 미달 · 1 오류.  "
    "생성물은 제안으로 보관되고 cta apply를 쳐야만 소스에 반영된다(v4 Step 3)",
    font=14,
    color="#495057",
    frame=f2,
)


def step(x, y, w, h, label, key, fr, font=13, llm_mark=False):
    fill, stroke = C[key]
    r = box(x, y, w, h, label, fill=fill, stroke=stroke, font=font, frame=fr)
    if llm_mark:
        box(x + w - 58, y - 14, 58, 24, "LLM", fill="#e03131", stroke="#e03131", font=12, frame=fr)
        elements[-1]["strokeColor"] = "#ffffff"
    return r


def chain(steps, y, fr, labels=None, x0=40, gap=70, h=90, widths=None):
    boxes = []
    x = x0
    for i, (label, key, mark) in enumerate(steps):
        w = widths[i] if widths else 230
        boxes.append(step(x, y, w, h, label, key, fr, llm_mark=mark))
        x += w + gap
    for i in range(len(boxes) - 1):
        a, b = boxes[i], boxes[i + 1]
        lab = labels[i] if labels and i < len(labels) else ""
        arrow(
            a,
            b,
            [(a["x"] + a["width"], y + h / 2), (b["x"], y + h / 2)],
            label=lab,
            frame=fr,
            stroke_w=2,
            free=True,
            font=11,
        )
    return boxes


# ── A. cta generate ──
text(
    40,
    Y0 + 130,
    "A. cta generate --class C  (테스트 생성 기능)",
    font=20,
    color=C["cli"][1],
    frame=f2,
)
gen = chain(
    [
        (
            "재료 수집\nadapters/materials.py\n테스트 없는 메서드 선정 · 확인 항목\n· 객체 생성법 · 기존 테스트 파일",
            "adapters",
            False,
        ),
        (
            "작성 엔진 (둘 중 하나)\nlegacy: core/writer_graph.py\ndeep: core/agent/ (메인+서브 3)\n도구 6개로 쓰기→실행→진단 반복 ≤8회",
            "core",
            True,
        ),
        (
            "게이트 ①~⑥ (결정적, R2)\n①assert ②스킵 ③범위 ④커버리지\n⑤PIT 뮤테이션 ⑥회귀\ncore/submit.py 탈락 시 재시도",
            "core",
            False,
        ),
        ("제안 저장\n.cta/proposals/\n(소스 미반영)", "state", False),
        ("cta diff → cta apply\n사람이 검토 후 반영\ncta discard 폐기", "cli", False),
    ],
    Y0 + 170,
    f2,
    labels=["재료", "run_writer\n계약", "통과\n(종료 0)", ""],
    widths=[280, 320, 320, 190, 220],
    h=100,
)
text(
    40,
    Y0 + 285,
    "탈락 사유 소진 → 사람 확인(종료 3) · 품질 미달(종료 2).  --record/--replay 로 LLM 호출 녹음·재생(--engine deep). --fast 는 ④⑤ 생략",
    font=12,
    color="#495057",
    frame=f2,
)

# ── B. cta maintain ──
text(
    40,
    Y0 + 340,
    "B. cta maintain --diff HEAD~1  (변경 대응 기능)",
    font=20,
    color=C["cli"][1],
    frame=f2,
)
mt = chain(
    [
        (
            "변경 추출\nadapters/changes.py\ngit diff → 변경 심볼 + 단서\n(시그니처·주석만·커밋 메시지·이슈)",
            "adapters",
            False,
        ),
        (
            "건별 의도 분류\nllm/intent.py\nbugfix / refactor / feature\n/ unclear (+확신도·근거)",
            "llm",
            True,
        ),
        (
            "검증 테스트 실행\n기존 테스트만 (R5 전체 실행 금지)\nadapters/runner → sandbox\n실패 내용 해석 failures.py",
            "adapters",
            False,
        ),
        (
            "조치 결정 규칙표\ncore/pipeline/decide.py\n의도 × 테스트 결과 → 경로\n(LLM 금지, R2·R3)",
            "core",
            False,
        ),
    ],
    Y0 + 380,
    f2,
    labels=["변경 묶음", "--intent로\n확정 가능", "실행 결과", ""],
    widths=[280, 280, 290, 280],
    h=100,
)
# 분기
dec = mt[-1]
bx = dec["x"] + dec["width"] + 40
create = step(
    bx,
    Y0 + 344,
    340,
    70,
    "create_test → A의 작성 엔진으로\n재발 방지 테스트 (수정 전 코드에서\n실패하는지 ⑥회귀 게이트 확인)",
    "core",
    f2,
    font=12,
)
esc = step(
    bx,
    Y0 + 430,
    340,
    70,
    "escalate / ask → .cta/escalations 저장\n후 멈춤 (종료 3). refactor+실패면\n기대값 갱신 없이 의심 위치만 정리",
    "state",
    f2,
    font=12,
)
arrow(
    dec,
    create,
    [(dec["x"] + dec["width"], Y0 + 420), (bx, Y0 + 379)],
    label="bugfix · feature",
    frame=f2,
    stroke_w=2,
    free=True,
    font=11,
    label_dy=-8,
)
arrow(
    dec,
    esc,
    [(dec["x"] + dec["width"], Y0 + 440), (bx, Y0 + 465)],
    label="refactor+실패 · unclear",
    frame=f2,
    stroke_w=2,
    color="#e03131",
    free=True,
    font=11,
    label_dy=40,
    label_dx=-50,
)
text(
    40,
    Y0 + 495,
    "trivial(주석만·포맷) 행은 규칙표에서 바로 종료 0.  판단 메모(.cta/memos)는 다음 maintain의 참고 자료.  --plan-only 는 결정까지만.",
    font=12,
    color="#495057",
    frame=f2,
)

# ── C. cta resolve ──
text(
    40,
    Y0 + 550,
    "C. cta resolve [id] --intended | --test-issue | --proceed | --as 의도 | --skip  (판단 전달 기능)",
    font=20,
    color=C["cli"][1],
    frame=f2,
)
rs = chain(
    [
        (
            "저장된 사람 확인 항목 읽기\n.cta/escalations/<id>.json\n(재개 지점 = 테스트 작성 단계 진입,\nADR-0015 D3)",
            "state",
            False,
        ),
        (
            "사람 결정 → 지침·허용 목록\ncli/resolve_cmd.py\n--intended: 의도된 변경 / --test-issue:\n테스트 문제 / --as: 의도 지정",
            "cli",
            False,
        ),
        ("A의 작성 엔진 + 게이트로 재개\n(create_test 경로 그대로)", "core", True),
        ("제안 + 판단 메모\n.cta/proposals · .cta/memos", "state", False),
    ],
    Y0 + 590,
    f2,
    labels=["", "", "통과"],
    widths=[290, 320, 290, 250],
    h=100,
)

# ── D. cta graph ──
text(
    40,
    Y0 + 730,
    "D. cta graph [--coverage]  (프로젝트 분석 기능, 선택)",
    font=20,
    color=C["cli"][1],
    frame=f2,
)
gg = chain(
    [
        (
            "Java 소스 파싱\nadapters/graph_builder.py\n클래스·메서드·테스트 노드\nDECLARES · CREATES 엣지",
            "adapters",
            False,
        ),
        (
            "JaCoCo 실측 (--coverage)\nadapters/coverage.py\n테스트 → 메서드 COVERS 엣지",
            "adapters",
            False,
        ),
        ("graph/neo4j_store.py\nNeo4j에 적재 (없으면\n인메모리·파싱 폴백)", "graph", False),
        (
            'query_code_graph 도구가 질의\n"기존 테스트 찾기"가 실측 기준\ngraph/answers.py',
            "core",
            False,
        ),
    ],
    Y0 + 770,
    f2,
    widths=[280, 280, 280, 290],
    h=90,
)

# 범례 (프레임 2)
lx = 1500
text(lx, Y0 + 730, "범례", font=16, frame=f2)
for i, (k, name) in enumerate(
    [
        ("cli", "cli 층"),
        ("adapters", "adapters/java 층"),
        ("core", "core 층 (언어 무관)"),
        ("llm", "llm 층"),
        ("graph", "graph 층"),
        ("state", ".cta/ 상태 파일"),
    ]
):
    box(lx, Y0 + 760 + i * 26, 26, 20, "", fill=C[k][0], stroke=C[k][1], frame=f2)
    text(lx + 36, Y0 + 760 + i * 26 + 1, name, font=13, frame=f2)
box(lx, Y0 + 760 + 6 * 26, 58, 24, "LLM", fill="#e03131", stroke="#e03131", font=12, frame=f2)
elements[-1]["strokeColor"] = "#ffffff"
text(
    lx + 70,
    Y0 + 760 + 6 * 26 + 3,
    "이 단계만 LLM 호출\n(llm/ 경유, 녹음·재생 가능)",
    font=13,
    frame=f2,
)

# ── 자리 유지용 빈 텍스트 제거 ──
elements[:] = [e for e in elements if not (e["type"] == "text" and e["text"] == "")]

# index(fractional index) 부여 — 단순 증가 문자열
for i, e in enumerate(elements):
    e["index"] = f"a{i:04d}"

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {
        "gridSize": 20,
        "gridStep": 5,
        "gridModeEnabled": False,
        "viewBackgroundColor": "#ffffff",
    },
    "files": {},
}

out = Path(sys.argv[1])
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {out} ({len(elements)} elements)")
