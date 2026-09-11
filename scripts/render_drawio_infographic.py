"""cta 아키텍처 인포그래픽 draw.io 문서(docs/architecture-infographic.drawio)를 생성한다.

글 대신 아이콘·짧은 이름으로 구조만 보여 주는 판이다(자세한 판은 docs/architecture.drawio).
페이지 1 "Agent Architecture": 사용자 → CLI → 에이전트(메인 + 서브 3 + 도구 6) ↔ LLM,
실행 장치·코드 그래프·대상 프로젝트, 게이트 → 제안 → 반영.
페이지 2 "Agent Workflow": 변경 → 의도 → 규칙표 → 작성 루프 → 게이트 → 제안 → 검토, 사람 확인 분기.
아이콘은 직접 그린 선 SVG를 데이터 URI로 넣는다 — 외부 서비스·이미지 파일 의존 없음.

사용:  python scripts/render_drawio_infographic.py docs/architecture-infographic.drawio
"""

# ruff: noqa: E501 — SVG 경로·그림 좌표 줄은 100자 규칙을 적용하지 않는다

import base64
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# ── 색 (인포그래픽용 — 층 색과 느슨하게 맞춘다) ─────────────────────────
INK = "#2b2b2b"
MUTED = "#6b7280"
BLUE = ("#e8f1fb", "#3b82c4")  # 사용자·CLI
GREEN = ("#e6f4ea", "#3a9a5b")  # 에이전트·core
RED = ("#fdecec", "#d64545")  # LLM
AMBER = ("#fff4dc", "#d9932a")  # 실행·어댑터
PURPLE = ("#efe9f8", "#7c5cbf")  # 그래프
GRAY = ("#f3f4f6", "#6b7280")  # 상태·게이트
PINK = ("#fce7f3", "#c2559a")  # 사람 개입


# ── 선 아이콘 (24x24, stroke 기반). 색은 넣을 때 정한다 ───────────────────
ICONS = {
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
    "robot": '<rect x="4" y="8" width="16" height="12" rx="3"/><circle cx="9" cy="14" r="1.5"/><circle cx="15" cy="14" r="1.5"/><path d="M12 8V4M9 4h6"/>',
    "chip": '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 3v3M12 3v3M15 3v3M9 18v3M12 18v3M15 18v3M3 9h3M3 12h3M3 15h3M18 9h3M18 12h3M18 15h3"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>',
    "pen": '<path d="M4 20l4-1 11-11-3-3L5 16l-1 4zM13 8l3 3"/>',
    "pulse": '<path d="M3 12h4l2-5 3 10 2-5h7"/>',
    "wrench": '<path d="M14 6a4 4 0 0 0 5 5l-9 9-3-3 9-9a4 4 0 0 0-2-2zM4 20l3-3"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "db": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "code": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M9 13l-2 2 2 2M15 13l2 2-2 2"/>',
    "git": '<circle cx="6" cy="5" r="2.5"/><circle cx="6" cy="19" r="2.5"/><circle cx="18" cy="9" r="2.5"/><path d="M6 7.5v9M18 11.5c0 3-3 4-6 4.5s-6 2-6 3"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M10 4v16"/>',
    "loop": '<path d="M20 12a8 8 0 0 1-14 5.3M4 12a8 8 0 0 1 14-5.3"/><path d="M4 8v4h4M20 16v-4h-4"/>',
    "pause": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
    "cloud": '<path d="M7 18a4 4 0 0 1-.6-8A6 6 0 0 1 18 9a4 4 0 0 1 0 9z"/>',
    "record": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="M10 8.5v7l5-3.5z"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    "box": '<path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
}


def icon_uri(name: str, color: str) -> str:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>'
    )
    return "data:image/svg+xml," + base64.b64encode(svg.encode()).decode()


class Page:
    def __init__(self, name: str) -> None:
        self.name = name
        self.cells: list[str] = []
        self._n = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    @staticmethod
    def _label(text: str) -> str:
        return escape(text, {'"': "&quot;"}).replace("\n", "&#xa;")

    def vertex(self, label, x, y, w, h, style, parent="1", cid=None) -> str:
        cid = cid or self._id("v")
        self.cells.append(
            f'<mxCell id="{cid}" value="{self._label(label)}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return cid

    def edge(self, src, dst, label="", style="", points=None, parent="1") -> str:
        cid = self._id("e")
        base = (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
            f"fontSize=12;fontColor={MUTED};labelBackgroundColor=#ffffff;strokeColor=#9ca3af;strokeWidth=2;endArrow=blockThin;endFill=1;"
        )
        pts = ""
        if points:
            pts = (
                '<Array as="points">'
                + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in points)
                + "</Array>"
            )
        self.cells.append(
            f'<mxCell id="{cid}" value="{self._label(label)}" style="{base}{style}" edge="1" parent="{parent}" source="{src}" target="{dst}">'
            f'<mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>'
        )
        return cid

    # ── 인포그래픽 부품 ──
    def card(
        self,
        x,
        y,
        w,
        h,
        icon,
        title,
        sub="",
        color=GREEN,
        parent="1",
        icon_size=40,
        title_size=15,
        cid=None,
    ):
        """아이콘 + 제목(+한 줄 부제)의 카드. 카드 자체가 연결 대상이다."""
        fill, stroke = color
        cid = self.vertex(
            "",
            x,
            y,
            w,
            h,
            f"rounded=1;arcSize=12;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=2;container=1;pointerEvents=0;",
            parent,
            cid,
        )
        self.vertex(
            "",
            (w - icon_size) / 2,
            12,
            icon_size,
            icon_size,
            f"shape=image;aspect=fixed;imageAspect=0;image={icon_uri(icon, stroke)};",
            cid,
        )
        label = (
            title
            if not sub
            else f"{title}\n<font style='font-size:11px' color='{MUTED}'>{sub}</font>"
        )
        self.vertex(
            label,
            4,
            12 + icon_size + 4,
            w - 8,
            h - icon_size - 20,
            f"text;html=1;align=center;verticalAlign=top;whiteSpace=wrap;fontSize={title_size};fontStyle=1;fontColor={INK};",
            cid,
        )
        return cid

    def chip(self, x, y, w, icon, title, color, parent="1", h=34, font=12):
        """아이콘 + 이름 한 줄의 작은 칩."""
        fill, stroke = color
        cid = self.vertex(
            "",
            x,
            y,
            w,
            h,
            f"rounded=1;arcSize=40;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};container=1;pointerEvents=0;",
            parent,
        )
        self.vertex(
            "",
            8,
            (h - 20) / 2,
            20,
            20,
            f"shape=image;aspect=fixed;image={icon_uri(icon, stroke)};",
            cid,
        )
        self.vertex(
            title,
            32,
            0,
            w - 36,
            h,
            f"text;html=1;align=left;verticalAlign=middle;whiteSpace=wrap;fontSize={font};fontColor={INK};",
            cid,
        )
        return cid

    def zone(self, x, y, w, h, title, color, dashed=False, cid=None):
        fill, stroke = color
        return self.vertex(
            title,
            x,
            y,
            w,
            h,
            f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};strokeWidth=1.5;verticalAlign=top;align=left;spacingLeft=14;spacingTop=6;fontSize=14;fontStyle=1;fontColor={stroke};container=1;pointerEvents=0;opacity=70;"
            + ("dashed=1;" if dashed else ""),
            "1",
            cid,
        )

    def text(self, label, x, y, w, h, font=13, color=MUTED, bold=False, align="left", parent="1"):
        return self.vertex(
            label,
            x,
            y,
            w,
            h,
            f"text;html=1;align={align};verticalAlign=top;whiteSpace=wrap;fontSize={font};fontColor={color};"
            + ("fontStyle=1;" if bold else ""),
            parent,
        )

    def badge(self, x, y, n, color=INK, parent="1", size=28):
        return self.vertex(
            str(n),
            x,
            y,
            size,
            size,
            f"ellipse;whiteSpace=wrap;html=1;fillColor={color};strokeColor=none;fontColor=#ffffff;fontSize=14;fontStyle=1;",
            parent,
        )

    def llm_tag(self, x, y, parent="1"):
        return self.vertex(
            "LLM",
            x,
            y,
            40,
            18,
            f"rounded=1;arcSize=50;whiteSpace=wrap;html=1;fillColor={RED[1]};strokeColor=none;fontColor=#ffffff;fontSize=10;fontStyle=1;",
            parent,
        )

    def xml(self) -> str:
        return (
            f'<diagram name="{escape(self.name)}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1654" pageHeight="1169" math="0" shadow="0" background="#ffffff">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            + "".join(self.cells)
            + "</root></mxGraphModel></diagram>"
        )


PIN = "exitX={ex};exitY={ey};exitDx=0;exitDy=0;entryX={nx};entryY={ny};entryDx=0;entryDy=0;"


def pin(ex, ey, nx, ny) -> str:
    return PIN.format(ex=ex, ey=ey, nx=nx, ny=ny)


# ═══════════════════════════════════════════════════════════════════════
# 페이지 1 — Agent Architecture
# ═══════════════════════════════════════════════════════════════════════
def page_architecture() -> Page:
    p = Page("Agent Architecture")
    p.text("Code Test Agent — Agent Architecture", 40, 20, 800, 34, font=26, color=INK, bold=True)
    p.text("Java 코드가 바뀌면 JUnit 테스트를 만들고 고치는 CLI 에이전트", 40, 58, 800, 24, font=14)

    # 왼쪽: 사용자 → CLI
    user = p.card(40, 130, 130, 110, "user", "사용자", "터미널 · CI", BLUE)
    cli = p.card(40, 290, 130, 110, "terminal", "cta CLI", "명령 3개", BLUE)
    p.edge(user, cli, "", pin(0.5, 1, 0.5, 0))

    # 가운데: 에이전트 영역
    agent = p.zone(240, 110, 720, 420, "AGENT  (LangGraph · Deep Agents)", GREEN, cid="agent")
    main = p.card(
        30, 50, 170, 110, "robot", "메인 에이전트", "계획 · 위임 · 판정", GREEN, parent=agent
    )
    p.llm_tag(180, 44, parent=agent)
    subs = []
    for i, (icon, name, sub) in enumerate(
        [
            ("search", "탐색", "코드 · 의존 · 유사 테스트"),
            ("pen", "작성", "테스트 쓰기 · 실행"),
            ("pulse", "진단", "반복 실패 원인"),
        ]
    ):
        subs.append(
            p.card(
                250 + i * 155,
                50,
                140,
                110,
                icon,
                name,
                sub,
                GREEN,
                parent=agent,
                icon_size=34,
                title_size=14,
            )
        )
        p.edge(
            main,
            subs[-1],
            "",
            pin(1, 0.5, 0, 0.5) if i == 0 else pin(1, 0.5, 0.5, 0),
            parent=agent,
            points=None if i == 0 else [(225, 105), (225, 30), (250 + i * 155 + 70, 30)],
        )
    # 도구 6개 줄
    p.text("도구 6개", 30, 190, 120, 22, font=13, color=GREEN[1], bold=True, parent=agent)
    tools = [
        ("search", "대상 조사"),
        ("db", "그래프 조회"),
        ("pen", "테스트 쓰기"),
        ("play", "테스트 실행"),
        ("eye", "품질 확인"),
        ("flag", "한계 보고"),
    ]
    for i, (icon, name) in enumerate(tools):
        p.chip(30 + i * 112, 216, 104, icon, name, GREEN, parent=agent)
    # 안전장치 줄
    p.text("안전장치 (LLM 없음)", 30, 275, 200, 22, font=13, color=GRAY[1], bold=True, parent=agent)
    for i, (icon, name) in enumerate(
        [
            ("loop", "반복 ≤ 8회"),
            ("pause", "4회마다 사람에게"),
            ("table", "규칙표"),
            ("shield", "게이트 6개"),
        ]
    ):
        p.chip(30 + i * 168, 301, 158, icon, name, GRAY, parent=agent)
    p.text(
        "한 번에 한 엔진 — legacy(LangGraph 서브그래프) 또는 deep(메인 + 서브 3)",
        30,
        350,
        660,
        20,
        font=11,
        parent=agent,
    )

    p.edge(cli, agent, "실행 요청", pin(1, 0.5, 0, 0.5))

    # 오른쪽: LLM
    llm = p.card(1050, 130, 170, 120, "chip", "LLM 게이트웨이", "Azure OpenAI 호환", RED)
    rec = p.card(
        1050,
        300,
        170,
        110,
        "record",
        "기록 · 재생",
        "카세트 (CI는 재생만)",
        RED,
        icon_size=34,
        title_size=14,
    )
    p.edge(agent, llm, "생성 · 판단", pin(1, 0.2, 0, 0.5))
    p.edge(llm, rec, "", pin(0.5, 1, 0.5, 0) + "dashed=1;endArrow=none;")

    # 아래: 실행 · 그래프 · 대상
    sandbox = p.card(240, 600, 190, 120, "gear", "실행 장치", "로컬 Maven · JDK / Docker", AMBER)
    graph = p.card(470, 600, 190, 120, "db", "코드 그래프", "Neo4j (선택)", PURPLE)
    target = p.card(700, 600, 190, 120, "code", "대상 프로젝트", "Maven · JUnit 5 · git", AMBER)
    p.edge(agent, sandbox, "테스트 실행", pin(0.15, 1, 0.5, 0))
    p.edge(agent, graph, "기존 테스트 찾기", pin(0.45, 1, 0.5, 0))
    p.edge(agent, target, "읽기 · 테스트 쓰기", pin(0.8, 1, 0.5, 0))

    # 결과 흐름: 게이트 → 제안 → 검토 → 반영
    gate = p.card(
        1050,
        470,
        170,
        120,
        "shield",
        "게이트 6개",
        "assert · 스킵 · 범위 · 커버리지 · 뮤테이션 · 회귀",
        GRAY,
        icon_size=36,
        title_size=14,
    )
    prop = p.card(
        1050, 640, 170, 110, "folder", "제안", ".cta/proposals", GRAY, icon_size=34, title_size=14
    )
    apply_ = p.card(
        1290,
        640,
        170,
        110,
        "check",
        "반영",
        "cta diff → cta apply",
        BLUE,
        icon_size=34,
        title_size=14,
    )
    p.edge(agent, gate, "생성 결과", pin(1, 0.75, 0, 0.5))
    p.edge(gate, prop, "통과", pin(0.5, 1, 0.5, 0))
    p.edge(
        gate,
        agent,
        "탈락 사유 → 재생성 (≤3회)",
        pin(0, 0.8, 0.97, 1) + "dashed=1;",
        points=[(938, 566)],
    )
    p.edge(prop, apply_, "사람 검토", pin(1, 0.5, 0, 0.5))
    p.edge(
        apply_,
        target,
        "src/test 에 쓰기",
        pin(0.5, 1, 1, 0.5) + "dashed=1;",
        points=[(1375, 780), (930, 780), (930, 660)],
    )

    # 원칙 3줄
    p.text(
        "<b>LLM은 두 곳에만</b> — 판단(의도 분류)과 작성.  <b>안전장치는 전부 일반 코드.</b>  <b>제안은 apply 전까지 소스에 닿지 않는다.</b>",
        240,
        760,
        1000,
        24,
        font=13,
        color=INK,
    )
    return p


# ═══════════════════════════════════════════════════════════════════════
# 페이지 2 — Agent Workflow
# ═══════════════════════════════════════════════════════════════════════
def page_workflow() -> Page:
    p = Page("Agent Workflow")
    p.text("Code Test Agent — Agent Workflow", 40, 20, 800, 34, font=26, color=INK, bold=True)
    p.text(
        "변경 감지부터 테스트 반영까지. 빨간 LLM 표시가 붙은 단계만 모델을 부른다",
        40,
        58,
        900,
        24,
        font=14,
    )

    Y = 150
    W, H, GAP = 160, 130, 60
    steps = [
        ("git", "변경 추출", "git diff → 바뀐 메서드", AMBER, False),
        ("chip", "의도 판단", "버그 수정 · 리팩터링 · 새 기능", RED, True),
        ("table", "규칙표", "의도 × 테스트 상태 → 조치", GRAY, False),
        ("robot", "테스트 작성", "쓰기 → 실행 → 진단 반복", GREEN, True),
        ("shield", "게이트 6개", "assert · 커버리지 · 뮤테이션 · 회귀 …", GRAY, False),
        ("folder", "제안", "소스 미반영", GRAY, False),
        ("check", "검토 · 반영", "cta diff → apply", BLUE, False),
    ]
    ids = []
    for i, (icon, title, sub, color, llm) in enumerate(steps):
        x = 40 + i * (W + GAP)
        cid = p.card(x, Y, W, H, icon, title, sub, color, icon_size=40, title_size=15)
        p.badge(x - 10, Y - 10, i + 1)
        if llm:
            p.llm_tag(x + W - 48, Y - 8)
        ids.append(cid)
    for a, b in zip(ids, ids[1:], strict=False):
        p.edge(a, b, "", pin(1, 0.5, 0, 0.5))

    # 작성 루프 (4번 아래)
    x4 = 40 + 3 * (W + GAP)
    loop_zone = p.zone(
        x4 + 20, Y + 190, 330, 150, "작성 루프 (최대 8회)", GREEN, dashed=True, cid="loop"
    )
    l1 = p.chip(15, 40, 90, "pen", "쓰기", GREEN, parent=loop_zone)
    l2 = p.chip(120, 40, 90, "play", "실행", GREEN, parent=loop_zone)
    l3 = p.chip(225, 40, 90, "pulse", "진단", GREEN, parent=loop_zone)
    p.edge(l1, l2, "", pin(1, 0.5, 0, 0.5), parent=loop_zone)
    p.edge(l2, l3, "실패", pin(1, 0.5, 0, 0.5), parent=loop_zone)
    p.edge(l3, l1, "", pin(0.5, 1, 0.5, 1), points=[(270, 92), (60, 92)], parent=loop_zone)
    p.chip(
        15,
        100,
        300,
        "pause",
        "4회마다 사람에게 묻기 · 같은 실패 반복이면 멈춤",
        GRAY,
        parent=loop_zone,
        font=11,
    )
    p.edge(ids[3], loop_zone, "", pin(0.5, 1, 0.2, 0) + "dashed=1;endArrow=none;")

    # 게이트 탈락 → 재생성
    p.edge(
        ids[4],
        ids[3],
        "탈락 사유 → 재생성 (≤3회)",
        pin(0.5, 0, 0.5, 0) + "dashed=1;",
        points=[(40 + 4 * (W + GAP) + 80, Y - 50), (x4 + 80, Y - 50)],
    )

    # 규칙표 분기 (3번 아래)
    x3 = 40 + 2 * (W + GAP)
    p.text("조치", x3 + 90, Y + H + 12, 60, 20, font=12, color=GRAY[1], bold=True)
    b1 = p.chip(x3 - 160, Y + 210, 220, "check", "테스트 만들기 → ④", GREEN)
    b2 = p.chip(x3 - 160, Y + 255, 220, "list", "할 일 없음", GRAY)
    b3 = p.chip(x3 - 160, Y + 300, 220, "pause", "사람 확인", PINK)
    p.edge(ids[2], b1, "", pin(0.5, 1, 1, 0.5), points=[(x3 + 80, Y + 227)])
    p.edge(ids[2], b2, "", pin(0.5, 1, 1, 0.5), points=[(x3 + 80, Y + 272)])
    p.edge(ids[2], b3, "", pin(0.5, 1, 1, 0.5), points=[(x3 + 80, Y + 317)])

    # 사람 확인 → resolve → 다시 ④
    human = p.card(
        x3 - 160,
        Y + 380,
        160,
        120,
        "user",
        "사람 판단",
        "cta resolve",
        PINK,
        icon_size=36,
        title_size=14,
    )
    p.edge(b3, human, "종료 코드 3 · 저장 후 멈춤", pin(0.5, 1, 0.5, 0))
    p.edge(
        human,
        ids[3],
        "의도됨 · 테스트 문제 · 건너뜀",
        pin(1, 0.5, 0.06, 1) + "dashed=1;",
        points=[(x3 + 160, Y + 440), (x3 + 160, Y + 360), (x4 + 10, Y + 360)],
    )
    # 리팩터링 + 실패 규칙
    p.text(
        "<b>리팩터링인데 테스트가 깨지면 기대값을 고치지 않는다</b> — 사람에게 넘긴다.",
        x3 + 200,
        Y + 420,
        420,
        40,
        font=12,
        color=INK,
    )

    # 하단 한 줄 요약
    p.text(
        "입력: 커밋(git diff) 또는 클래스 이름   ·   출력: 제안(.cta/proposals)   ·   종료 코드: 0 완료 · 3 사람 확인 · 2 품질 미달 · 1 오류",
        40,
        Y + 560,
        1400,
        24,
        font=13,
    )
    return p


def main() -> None:
    out = Path(sys.argv[1])
    pages = [page_architecture(), page_workflow()]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="drawio" version="26.0.0" type="device">'
        + "".join(pg.xml() for pg in pages)
        + "</mxfile>\n"
    )
    out.write_text(xml, encoding="utf-8")
    print(f"wrote {out} ({sum(len(pg.cells) for pg in pages)} cells, {len(pages)} pages)")


if __name__ == "__main__":
    main()
