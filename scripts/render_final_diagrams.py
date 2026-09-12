"""최종산출물/cta-diagrams.drawio — 현재 프로젝트 기준 그림 6장(6페이지)을 생성한다.

1. Agent Architecture (인포그래픽)   — render_final_infographic.page_architecture_v2
2. Detailed Architecture (상세 설명)  — render_drawio.page_agent + 오늘 수정 반영(같은 이름 교체·제안 이어붙임)
3. User Command Flows (명령어별 흐름) — render_drawio.page_cli + 오늘 수정 반영
4. Graph DB Architecture (인포그래픽) — 이 파일에서 새로 그린다: 노드 2종·엣지 4종, 채우는 쪽(파싱·JaCoCo·CALLS 추정),
   질의 4종과 소비처(도구·TestLocator·ImpactFinder), Neo4j 없을 때의 폴백, 샌드박스 밖 배치·단일 라벨 설계.
5. CLI Flows (인포그래픽 간소화)      — 명령 한 줄 = 카드 몇 장. 3페이지의 상세 레인을 발표용으로 줄인 판.
6. Project Structure (간소화)         — 층별 구역 + '파일 — 한 줄 설명' 칩, 핵심 파일만.
외부 서비스·이미지 파일 의존 없음.

사용:  python scripts/render_final_diagrams.py 최종산출물/cta-diagrams.drawio
"""

# ruff: noqa: E501 — 그림 좌표·문구 줄은 100자 규칙을 적용하지 않는다

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_drawio as detail  # noqa: E402
from render_drawio_infographic import (  # noqa: E402
    AMBER,
    BLUE,
    GRAY,
    GREEN,
    INK,
    PINK,
    PURPLE,
    RED,
    Page,
    pin,
)
from render_final_infographic import page_architecture_v2  # noqa: E402


def _replace(page, pairs):
    """생성된 셀 문자열에서 문구를 바꾼다 — 기존 페이지 함수를 건드리지 않고 오늘 변경분만 얹는다."""
    for old, new in pairs:
        page.cells = [c.replace(old, new) for c in page.cells]
    return page


def page_detail():
    p = detail.page_agent()
    p.name = "2. Detailed Architecture"
    return _replace(
        p,
        [
            (
                "writer.py + merge.py&#xa;쓰기·컴파일 검사",
                "writer.py + merge.py&#xa;쓰기·컴파일 · 같은 이름 메서드는 제자리 교체",
            ),
            (
                "proposals/ 제안&#xa;cta diff → apply / discard",
                "proposals/ 제안 (같은 클래스는 이어 붙임)&#xa;cta diff → apply / discard",
            ),
        ],
    )


def page_flows():
    p = detail.page_cli()
    p.name = "3. User Command Flows"
    return _replace(
        p,
        [
            (
                "게이트 재시도 소진 → 사람 확인(종료 3) · 품질 미달(종료 2).",
                "같은 테스트 클래스의 대기 제안이 있으면 그 위에 이어서 생성(덮어쓰지 않음). 게이트 재시도 소진 → 사람 확인(종료 3) · 품질 미달(종료 2).",
            ),
            (
                "판단 메모는 상황 요약(커밋 메시지·대상·분석, 자연어)을 임베딩해 저장하고, 다음 maintain에서 이름 일치 + 코사인 유사도로 참고 자료가 된다(ADR-0026 D3).",
                "--intended/--test-issue는 실패한 테스트 메서드를 제자리에서 교체한다(허용 목록 밖은 assert 게이트가 보호). 재개가 실패하면 항목을 지우지 않고 --hint 재시도를 안내한다. 판단 메모는 상황 요약을 임베딩해 저장하고 다음 maintain에서 이름 일치 + 코사인으로 참고 자료가 된다.",
            ),
        ],
    )


def page_graphdb() -> Page:
    p = Page("4. Graph DB Architecture")
    p.text(
        "Code Test Agent — Graph DB Architecture", 40, 20, 900, 34, font=26, color=INK, bold=True
    )
    p.text(
        "코드 그래프: 확정 관계 3종 + 추정 관계 1종을 Neo4j(선택)에 두고, 사전 정의 질의 4종으로만 읽는다. 없으면 파싱 폴백 — 그래프는 필수가 아니다",
        40,
        58,
        1300,
        24,
        font=14,
    )

    # ── 왼쪽: 채우는 쪽 (cta graph) ──
    zs = p.zone(40, 110, 430, 560, "채우기 — cta graph [--coverage]", AMBER, cid="zs")
    s1 = p.card(
        30,
        50,
        170,
        120,
        "code",
        "Java 소스",
        "src/main · src/test",
        AMBER,
        parent=zs,
        icon_size=36,
        title_size=14,
    )
    s2 = p.card(
        230,
        50,
        170,
        120,
        "search",
        "정적 파싱",
        "graph_builder.py (정규식)",
        AMBER,
        parent=zs,
        icon_size=36,
        title_size=14,
    )
    s3 = p.card(
        30,
        210,
        170,
        120,
        "link",
        "호출 관계 추정",
        "calls.py · 확신도 high/medium",
        PURPLE,
        parent=zs,
        icon_size=36,
        title_size=14,
    )
    s4 = p.card(
        230,
        210,
        170,
        120,
        "play",
        "JaCoCo 실측",
        "coverage.py · 테스트별 격리 실행",
        AMBER,
        parent=zs,
        icon_size=36,
        title_size=14,
    )
    p.edge(s1, s2, "", pin(1, 0.5, 0, 0.5), parent=zs)
    p.edge(s2, s3, "", pin(0.5, 1, 0.5, 0), parent=zs, points=[(315, 190), (115, 190)])
    p.edge(s2, s4, "--coverage", pin(0.5, 1, 0.5, 0), parent=zs)
    p.chip(
        30,
        370,
        370,
        "table",
        "노드: Class · Method (is_test · param_count · uses_exception · snippet 600자)",
        GRAY,
        parent=zs,
        font=11,
    )
    p.chip(30, 415, 370, "table", "엣지: DECLARES · CREATES (정적, 확정)", GRAY, parent=zs, font=11)
    p.chip(
        30,
        460,
        370,
        "shield",
        "엣지: COVERS (커버리지 실측, 확정) — 추측 아님",
        GRAY,
        parent=zs,
        font=11,
    )
    p.chip(
        30,
        505,
        370,
        "link",
        "엣지: CALLS (정적 추정, confidence · excerpt 필수)",
        PURPLE,
        parent=zs,
        font=11,
    )

    # ── 가운데: 저장소 ──
    zd = p.zone(570, 110, 400, 560, "저장 — GraphStore 포트", PURPLE, cid="zd")
    neo = p.card(
        30,
        60,
        340,
        150,
        "db",
        "Neo4j (선택)",
        "샌드박스 밖 별도 컨테이너 · bolt · 접속 정보는 .env(CTA_NEO4J_*)",
        PURPLE,
        parent=zd,
        icon_size=44,
        title_size=16,
    )
    mem = p.card(
        30,
        240,
        340,
        120,
        "box",
        "인메모리 저장소",
        "테스트 · 폴백(그 자리 파싱) — 같은 GraphStore 계약",
        GRAY,
        parent=zd,
        icon_size=36,
        title_size=14,
    )
    p.chip(
        30,
        390,
        340,
        "table",
        "단일 라벨 CodeNode · 단일 관계 REL + kind 속성",
        GRAY,
        parent=zd,
        font=11,
    )
    p.chip(
        30,
        435,
        340,
        "shield",
        "Cypher는 고정 문자열 + 파라미터 — 주입·캐시 미스 없음",
        GRAY,
        parent=zd,
        font=11,
    )
    p.chip(
        30,
        480,
        340,
        "folder",
        "project 속성으로 여러 프로젝트가 한 DB에 공존",
        GRAY,
        parent=zd,
        font=11,
    )
    p.text(
        "빌드 = replace_project(프로젝트 단위 전체 교체). 증분 갱신은 후순위",
        30,
        525,
        340,
        20,
        font=11,
        parent=zd,
    )
    p.edge(zs, neo, "저장", pin(1, 0.25, 0, 0.5))
    p.edge(zs, mem, "접속 실패 시", pin(1, 0.55, 0, 0.5) + "dashed=1;")

    # ── 오른쪽: 읽는 쪽 ──
    zq = p.zone(
        1040,
        110,
        700,
        560,
        "읽기 — 사전 정의 질의만 (자유 Cypher 금지, 답 800토큰 상한)",
        GREEN,
        cid="zq",
    )
    queries = [
        ("search", "verifying_tests", "COVERS 실측 → 검증하는 테스트", GRAY),
        ("wrench", "how_to_create", "CREATES → 생성 코드(테스트 우선)", GRAY),
        ("eye", "similar_tests", "모양 거리 → few-shot 본보기 2건", GRAY),
        ("link", "callers", "CALLS → 호출자 [high/medium] '정적 추정' 표기", PURPLE),
    ]
    qids = []
    for i, (icon, name, sub, color) in enumerate(queries):
        x = 30 + (i % 2) * 330
        y = 50 + (i // 2) * 140
        qids.append(
            p.card(x, y, 310, 120, icon, name, sub, color, parent=zq, icon_size=34, title_size=14)
        )
    p.text(
        "저장소 API: neighbors · edges_in · methods_by_kind (Cypher는 여기서만) · 후순위 질의(안내 문장): implementations · touches_outside",
        30,
        330,
        640,
        20,
        font=11,
        parent=zq,
    )
    p.chip(30, 365, 200, "gear", "query_code_graph 도구", GREEN, parent=zq, font=11)
    p.chip(250, 365, 200, "check", "TestLocator (COVERS)", GREEN, parent=zq, font=11)
    p.chip(470, 365, 200, "list", "ImpactFinder (CALLS)", PURPLE, parent=zq, font=11)
    p.text(
        "쓰임: 도구는 에이전트(탐색·진단)가 부른다 · TestLocator는 maintain의 '기존 테스트 상태'(규칙표 입력, 실측만) ·\nImpactFinder는 영향 범위(화면·지침서·--impact) — 추정이라 규칙표에는 넣지 않는다",
        30,
        410,
        640,
        60,
        font=11,
        parent=zq,
    )
    p.chip(
        30,
        480,
        640,
        "shield",
        "그래프에 있으면 사실이다 — 확정 엣지만 조치 결정에 쓰고, 추정(CALLS)은 표기와 함께 참고로만",
        GRAY,
        parent=zq,
        font=11,
    )
    p.edge(neo, zq, "질의", pin(1, 0.5, 0, 0.3))
    p.edge(mem, zq, "", pin(1, 0.5, 0, 0.55) + "dashed=1;")

    # ── 아래: 예시 ──
    p.text(
        "<b>예</b> — demo 프로젝트: OrderService#findById ←COVERS— OrderServiceTest (실측) · OrderService#findById ←CALLS[high]— OrderController#get, OrderService#pay·cancel·updateAmount (추정) · OrderService#applyDiscount ←COVERS 없음 = '검증하는 테스트가 없다'가 바로 읽힌다",
        40,
        700,
        1630,
        40,
        font=12,
        color=INK,
    )
    return p


def page_cli_infographic() -> Page:
    """5. CLI 명령별 흐름 — 인포그래픽 간소화 판. 명령 한 줄 = 카드 몇 장, 글은 최소."""
    p = Page("5. CLI Flows (Infographic)")
    p.text("Code Test Agent — CLI Flows", 40, 20, 900, 34, font=26, color=INK, bold=True)
    p.text(
        "명령 하나 = 한 줄. 빨간 LLM 표시가 붙은 카드만 모델을 부른다. 생성물은 언제나 '제안'이고 apply를 쳐야 소스에 닿는다",
        40,
        58,
        1300,
        24,
        font=14,
    )
    W, H, GAP, Y0, ROW = 180, 112, 40, 110, 185

    def row(index, title, color, cards, note="", arrows=None):
        """arrows: 화살표로 이을 카드 수(None=전부). 독립 명령(D의 discard, E 전부)은 잇지 않는다."""
        zone = p.zone(40, Y0 + index * ROW, 1700, 165, title, color, cid=f"row{index}")
        ids = []
        for i, (icon, name, sub, c, llm) in enumerate(cards):
            x = 30 + i * (W + GAP)
            ids.append(
                p.card(x, 42, W, H, icon, name, sub, c, parent=zone, icon_size=30, title_size=13)
            )
            if llm:
                p.llm_tag(x + W - 46, 36, parent=zone)
        linked = ids if arrows is None else ids[:arrows]
        for a, b in zip(linked, linked[1:], strict=False):
            p.edge(a, b, "", pin(1, 0.5, 0, 0.5), parent=zone)
        if note:
            p.text(
                note,
                30 + len(cards) * (W + GAP),
                54,
                1700 - 60 - len(cards) * (W + GAP),
                90,
                font=11,
                parent=zone,
            )
        return zone, ids

    row(
        0,
        "A · cta generate --class C  [--max-methods N] [--fast]",
        BLUE,
        [
            ("search", "재료 수집", "테스트 없는 메서드 · 확인 항목", AMBER, False),
            ("robot", "테스트 작성", "쓰기 → 실행 → 진단 (≤8회)", GREEN, True),
            ("shield", "게이트 6개", "assert · 스킵 · 범위 · 커버리지 · 뮤테이션", GRAY, False),
            ("folder", "제안", ".cta/proposals (소스 미반영)", GRAY, False),
            ("check", "종료 0 / 2 / 3", "완료 · 품질 미달 · 사람 확인", BLUE, False),
        ],
        "게이트 탈락 → 사유를 붙여 재생성(≤3회). 같은 테스트 클래스의 대기 제안이 있으면 그 위에 이어서 생성한다.",
    )
    row(
        1,
        "B · cta maintain --diff HEAD~1  [--intent 의도] [--message …] [--impact]",
        AMBER,
        [
            ("git", "변경 추출", "git diff → 바뀐 메서드 + 단서", AMBER, False),
            ("chip", "의도 판단", "버그 수정·리팩터링·새 기능·불확실", RED, True),
            ("play", "기존 테스트 실행", "통과/실패/없음 · 영향 범위", AMBER, False),
            ("table", "규칙표", "의도 × 테스트 상태 → 조치 (LLM 없음)", GRAY, False),
            ("robot", "테스트 만들기", "A의 작성·게이트 → 제안", GREEN, True),
            ("pause", "사람 확인", "리팩터링+실패 · 불확실 → 저장 후 멈춤(종료 3)", PINK, False),
        ],
        "--impact: 확신 high 호출자에도 생성(↳ 파생 건). 판단 메모(이름 일치 + 임베딩)를 참고로 보여 준다.",
    )
    row(
        2,
        "C · cta resolve <id>  --intended | --test-issue | --proceed | --as 의도 | --skip",
        PINK,
        [
            ("user", "사람 판단", "선택지 하나를 명시", PINK, False),
            ("folder", "저장 항목 읽기", ".cta/escalations/<id>", GRAY, False),
            ("robot", "재개", "실패 테스트만 제자리 교체", GREEN, True),
            ("shield", "게이트", "허용 목록 밖 assert 변경은 탈락", GRAY, False),
            ("vector", "판단 메모", "상황 요약 + 임베딩 저장", PINK, True),
            ("folder", "제안", "실패 시 항목 유지 → --hint", GRAY, False),
        ],
    )
    row(
        3,
        "D · cta diff [이름]  ·  cta apply [이름 | --all]  ·  cta discard",
        GREEN,
        [
            ("eye", "diff 검토", "현재 파일 vs 제안", GRAY, False),
            ("user", "사람 결정", "반영할까 / 버릴까", PINK, False),
            ("check", "apply", "src/test에 쓰기 (이때만 반영)", BLUE, False),
            ("flag", "discard", "제안 폐기 (소스 무변경)", GRAY, False),
        ],
        "생성물은 apply 전까지 소스에 닿지 않는다(v4 Step 3). CI는 종료 코드로 분기한다.",
        arrows=3,
    )
    row(
        4,
        "E · cta graph [--coverage]  ·  cta eval [--intents]  ·  cta demo",
        PURPLE,
        [
            ("db", "graph", "정적 파싱 + 실측 → Neo4j(선택)", PURPLE, False),
            ("pulse", "eval", "검출률 · 의도 분류 정확도", AMBER, True),
            ("record", "demo", "저장된 호출 기록 재생 — 비용 0", RED, False),
        ],
        "graph는 '기존 테스트 찾기'를 실측 기준으로 바꾼다(없으면 파싱 폴백). eval·demo는 개발·시연용.",
        arrows=0,
    )
    p.text(
        "종료 코드: 0 정상 완료 · 3 사람 확인 필요(실패 아님) · 2 품질 미달 · 1 오류      공통 옵션: --non-interactive · --quiet · --runner docker · --engine deep",
        40,
        Y0 + 5 * ROW + 10,
        1700,
        24,
        font=13,
        color=INK,
    )
    return p


def page_structure() -> Page:
    """6. 프로젝트 파일 구조 — 트리(파일 탐색기) 형태. 폴더 → 파일로 연결선, 노드마다 한 줄 설명. 핵심 파일만."""
    p = Page("6. Project Structure")
    p.text("Code Test Agent — Project Structure", 40, 20, 900, 34, font=26, color=INK, bold=True)
    p.text(
        "트리는 핵심 파일만 담았다(테스트·캐시·__init__ 생략). 색 = 층(core 초록 · adapters 노랑 · graph 보라 · llm 빨강 · sandbox 주황 · cli 파랑 · 그 밖 회색)",
        40,
        58,
        1500,
        24,
        font=14,
    )
    STEP, IND, H = 33, 34, 27
    EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;strokeColor=#9ca3af;strokeWidth=1.5;endArrow=none;exitX=0.02;exitY=1;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"

    def tree(x0, y0, w, nodes):
        """nodes: (depth, icon, name, desc, color). 같은 깊이의 직전 노드가 아니라 얕은 직전 노드가 부모다."""
        stack: dict[int, str] = {}
        y = y0
        for depth, icon, name, desc, color in nodes:
            label = f"<b>{name}</b>" + (f"  <font color='#6b7280'>— {desc}</font>" if desc else "")
            cid = p.chip(x0 + depth * IND, y, w - depth * IND, icon, label, color, h=H, font=11)
            parent = stack.get(depth - 1)
            if parent is not None:
                p.edge(parent, cid, "", EDGE)
            stack[depth] = cid
            for d in [k for k in stack if k > depth]:
                del stack[d]
            y += STEP
        return y

    D, F = "folder", "code"
    # ── 열 1: 루트와 층 폴더, cta/core·graph·sandbox ──
    tree(
        40,
        110,
        540,
        [
            (0, D, "skax-master-project/", "리포지토리 루트", GRAY),
            (1, D, "cta/", "제품 코드 — 층 6개", GREEN),
            (2, D, "core/", "핵심 로직 · 언어를 모른다(R1)", GREEN),
            (3, F, "ports.py", "포트(인터페이스) 9종", GREEN),
            (3, D, "pipeline/", "decide(규칙표) · maintain(변경 대응) · models", GREEN),
            (3, D, "tools/", "고유 도구 6개, 1도구 1파일", GREEN),
            (3, F, "writer_graph.py", "legacy 작성 루프(LangGraph, ≤8회)", GREEN),
            (3, D, "agent/", "Deep Agent 메인+서브 3 · limits 원장 · prompts/", GREEN),
            (3, F, "gates.py · submit.py", "게이트 계약 · 생성→게이트 재시도(≤3회)", GREEN),
            (3, F, "config.py", "cta.toml — 기준치·상한·모델·예산·[impact]", GREEN),
            (2, D, "graph/", "코드 그래프 (Neo4j 선택)", PURPLE),
            (3, F, "model.py", "노드 2종 · 엣지 4종(+CALLS 확신도)", PURPLE),
            (3, F, "store.py · neo4j_store.py", "GraphStore — 인메모리 / Neo4j", PURPLE),
            (3, F, "answers.py · impact.py", "질의 → 답 · CALLS → 호출자(ImpactFinder)", PURPLE),
            (2, D, "sandbox/", "실행 장치 (R6)", AMBER),
            (3, F, "local_sandbox.py", "이 PC의 Maven·JDK (기본)", AMBER),
            (3, F, "docker_sandbox.py · factory.py", "격리 컨테이너 · 선택기", AMBER),
            (2, D, "adapters/java/", "열 2에 펼침", AMBER),
            (2, D, "llm/", "열 2에 펼침", RED),
            (2, D, "cli/", "열 3에 펼침", BLUE),
            (2, D, "evals/", "열 3에 펼침", GRAY),
        ],
    )
    # ── 열 2: adapters/java · llm ──
    tree(
        620,
        110,
        560,
        [
            (0, D, "cta/adapters/java/", "포트의 Java·Maven 구현", AMBER),
            (1, F, "parsing.py", "정규식 파서(메서드·assert·패키지)", AMBER),
            (1, F, "materials.py", "재료 수집 — 메서드 선정·확인 항목·생성법", AMBER),
            (1, F, "changes.py", "git diff → 변경 심볼+단서 · 참조 파싱 TestLocator", AMBER),
            (
                1,
                F,
                "graph_builder.py · calls.py",
                "소스 → 노드·엣지 · 호출 관계 추정(확신도)",
                AMBER,
            ),
            (1, F, "coverage.py", "JaCoCo 실측 → COVERS · 커버리지 게이트 재료", AMBER),
            (1, F, "gates.py", "assert·스킵·범위·커버리지 게이트(줄 원문 첨부)", AMBER),
            (1, F, "mutation.py · regression.py", "PIT 뮤테이션 · 수정 전 코드 회귀 게이트", AMBER),
            (
                1,
                F,
                "writer.py · merge.py",
                "쓰기·컴파일 검사 · 조각 병합(같은 이름 제자리 교체)",
                AMBER,
            ),
            (
                1,
                F,
                "runner.py · inspector.py · similar.py",
                "선택 실행(R5) · 대상 조사 · 유사 테스트 폴백",
                AMBER,
            ),
            (1, D, "skills/", "작성 지식 규칙 SKILL.md (junit5-mockito · regression-test)", AMBER),
            (0, D, "cta/llm/", "LLM 호출의 유일한 통로 (R7)", RED),
            (1, F, "config.py · gateway.py", "클라이언트 생성 입구 · 게이트웨이 HTTP", RED),
            (
                1,
                F,
                "chat_model.py · model_cassette.py",
                "LangChain 모델 · 카세트 v2 미들웨어(deep)",
                RED,
            ),
            (
                1,
                F,
                "generation.py · intent.py",
                "테스트 작성 · 의도 분류 — LLM이 있는 두 자리",
                RED,
            ),
            (1, F, "embeddings.py", "판단 메모 상황 임베딩 — 자연어만, 기록·재생", RED),
            (1, F, "replay.py", "호출 기록·재생 v1 — 어긋나면 실패, 폴백 없음", RED),
            (1, F, "metering.py · masking.py", "토큰 합산·예산 · 시크릿 가림", RED),
            (1, D, "prompts/", "system · write_test(_append) · classify_intent", RED),
        ],
    )
    # ── 열 3: cli · evals · 그 밖 ──
    tree(
        1220,
        110,
        540,
        [
            (0, D, "cta/cli/", "명령 조립·입출력 (판단 로직 없음)", BLUE),
            (1, F, "main.py", "진입점 cta <명령> · UTF-8 콘솔 · 오류 안내", BLUE),
            (1, F, "generate.py", "재료 → 엔진 → 게이트 → 제안 (공용 진입)", BLUE),
            (
                1,
                F,
                "maintain_cmd.py · resolve_cmd.py",
                "변경 대응(--impact) · 사람 판단 재개",
                BLUE,
            ),
            (
                1,
                F,
                "proposals.py · escalations.py · memos.py",
                ".cta/ 제안 · 사람 확인 항목 · 판단 메모",
                BLUE,
            ),
            (
                1,
                F,
                "render.py · hints.py · locate.py",
                "화면 형식 · 오류 3줄 안내 · 프로젝트 탐색",
                BLUE,
            ),
            (1, F, "graph_cmd.py · eval_cmd.py · demo_cmd.py", "cta graph · eval · demo", BLUE),
            (0, D, "cta/evals/", "평가 재료", GRAY),
            (1, D, "defects/ · intents/", "결함 세트 12건 · 의도 세트 10건", GRAY),
            (1, D, "golden/ · results/", "대표 시나리오 기록 · 실측 결과 JSON", GRAY),
            (0, D, "skax-master-project/ (계속)", "루트의 나머지", GRAY),
            (1, D, "tests/", "단위 테스트 39 파일 · 314건 (Fake·기록 재생, 층 규칙 검사)", GRAY),
            (1, D, "scripts/", "그림 생성 · 기록 재생성 · 결함 점검", GRAY),
            (1, D, "examples/", "demo · evalbench — 대상 Maven 프로젝트 예제", GRAY),
            (1, D, "docs/ · docs/adr/", "설계(v4)·계약·ADR-0010~0026 — 과거 문서는 동결", GRAY),
            (1, D, "최종산출물/", "이 그림들 (cta-diagrams.drawio + PNG)", GRAY),
            (1, F, "pyproject.toml", "의존성 · cta 진입점 · ruff·pytest 설정", GRAY),
            (1, F, "CLAUDE.md · README.md", "절대 규칙 R1~R7 · 사용법", GRAY),
            (1, F, ".env.example · cta.toml", "설정 키 이름(값 없음) · 프로젝트 설정", GRAY),
        ],
    )
    return p


def main() -> None:
    out = Path(sys.argv[1])
    p1 = page_architecture_v2()
    p1.name = "1. Agent Architecture"
    pages = [
        p1,
        page_detail(),
        page_flows(),
        page_graphdb(),
        page_cli_infographic(),
        page_structure(),
    ]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="drawio" version="26.0.0" type="device">'
        + "".join(pg.xml() for pg in pages)
        + "</mxfile>\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml, encoding="utf-8")
    print(f"wrote {out} ({sum(len(pg.cells) for pg in pages)} cells, {len(pages)} pages)")


if __name__ == "__main__":
    main()
