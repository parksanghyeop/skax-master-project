"""cta 아키텍처 draw.io 문서(docs/architecture.drawio)를 생성한다 — 산출물 재생성용.

페이지 1 "에이전트 구조": 작성 엔진 둘(legacy LangGraph 서브그래프 · Deep Agent 메인+서브 3),
고유 도구 6개 → 포트 → 어댑터 → 실행 장치, llm 층, 안전장치(게이트·규칙표·반복 상한·사람 개입).
페이지 2 "CLI 명령별 흐름": generate / maintain / resolve / diff·apply·discard / graph 레인.
근거: docs/architecture.md, cta/core/agent/*, cta/core/writer_graph.py, cta/core/submit.py,
cta/core/pipeline/decide.py, cli/*. 외부 서비스에 아무것도 보내지 않고 XML을 직접 쓴다.

사용:  python scripts/render_drawio.py docs/architecture.drawio
PNG:   "C:/Program Files/draw.io/draw.io.exe" -x -f png --width 2400 -p 0 -o out.png docs/architecture.drawio
"""

# ruff: noqa: E501 — 그림 안 글자 문자열은 줄바꿈 표시 위치가 곧 상자 줄바꿈이라 100자 규칙을 적용하지 않는다

import sys
from pathlib import Path
from xml.sax.saxutils import escape

# ── 팔레트 (draw.io 기본 팔레트, 층별 고정) ─────────────────────────────
C = {
    "cli": ("#dae8fc", "#6c8ebf"),
    "core": ("#d5e8d4", "#82b366"),
    "adapters": ("#fff2cc", "#d6b656"),
    "llm": ("#f8cecc", "#b85450"),
    "graph": ("#e1d5e7", "#9673a6"),
    "sandbox": ("#ffe6cc", "#d79b00"),
    "state": ("#f5f5f5", "#666666"),
    "ext": ("#ffffff", "#666666"),
    "human": ("#fce8f6", "#b5739d"),
}


class Page:
    """한 페이지의 셀 목록. id는 페이지 안에서 유일하면 된다."""

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

    def vertex(
        self,
        label: str,
        x: float,
        y: float,
        w: float,
        h: float,
        style: str,
        parent: str = "1",
        cid: str | None = None,
    ) -> str:
        cid = cid or self._id("v")
        self.cells.append(
            f'<mxCell id="{cid}" value="{self._label(label)}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return cid

    def edge(
        self,
        src: str,
        dst: str,
        label: str = "",
        style: str = "",
        points: list[tuple[float, float]] | None = None,
        parent: str = "1",
    ) -> str:
        cid = self._id("e")
        base = "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;fontSize=11;labelBackgroundColor=#ffffff;"
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

    # ── 자주 쓰는 모양 ──
    def box(
        self,
        label,
        x,
        y,
        w,
        h,
        key,
        parent="1",
        font=12,
        bold=False,
        dashed=False,
        align="center",
        cid=None,
    ):
        fill, stroke = C[key]
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontSize={font};align={align};"
            + ("fontStyle=1;" if bold else "")
            + ("dashed=1;" if dashed else "")
            + ("spacingLeft=6;" if align == "left" else "")
        )
        return self.vertex(label, x, y, w, h, style, parent, cid)

    def lane(self, label, x, y, w, h, key, parent="1", font=13, cid=None, start=30):
        fill, stroke = C[key]
        style = f"swimlane;startSize={start};html=1;fillColor={fill};strokeColor={stroke};fontSize={font};fontStyle=1;whiteSpace=wrap;"
        return self.vertex(label, x, y, w, h, style, parent, cid)

    def text(
        self, label, x, y, w, h, font=12, parent="1", align="left", color="#333333", bold=False
    ):
        style = (
            f"text;html=1;align={align};verticalAlign=top;whiteSpace=wrap;fontSize={font};fontColor={color};"
            + ("fontStyle=1;" if bold else "")
        )
        return self.vertex(label, x, y, w, h, style, parent)

    def ellipse(self, label, x, y, w, h, key="core", parent="1", font=12):
        fill, stroke = C[key]
        return self.vertex(
            label,
            x,
            y,
            w,
            h,
            f"ellipse;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontSize={font};",
            parent,
        )

    def rhombus(self, label, x, y, w, h, parent="1", font=11):
        return self.vertex(
            label,
            x,
            y,
            w,
            h,
            f"rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize={font};",
            parent,
        )

    def xml(self) -> str:
        return (
            f'<diagram name="{escape(self.name)}"><mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1654" pageHeight="1169" math="0" shadow="0">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            + "".join(self.cells)
            + "</root></mxGraphModel></diagram>"
        )


PIN = "exitX={ex};exitY={ey};exitDx=0;exitDy=0;entryX={nx};entryY={ny};entryDx=0;entryDy=0;"


def pin(ex, ey, nx, ny) -> str:
    return PIN.format(ex=ex, ey=ey, nx=nx, ny=ny)


LLM_BADGE = "rounded=1;whiteSpace=wrap;html=1;fillColor=#b85450;strokeColor=#b85450;fontColor=#ffffff;fontSize=10;fontStyle=1;"


# ═══════════════════════════════════════════════════════════════════════
# 페이지 1 — 에이전트 구조 아키텍처
# ═══════════════════════════════════════════════════════════════════════
def page_agent() -> Page:
    p = Page("1. 에이전트 구조")
    p.text(
        "Code Test Agent (cta) — 에이전트 구조 아키텍처",
        40,
        20,
        900,
        30,
        font=22,
        bold=True,
        color="#1e1e1e",
    )
    p.text(
        "LLM이 있는 곳은 llm 층 하나뿐(빨강). 작성 엔진은 둘이 공존하고(--engine legacy|deep) 게이트 루프는 둘을 같은 run_writer 계약으로 부른다. "
        "안전장치(게이트·규칙표·반복 상한·사람 개입)는 전부 일반 코드(R2). 실선 = 호출, 점선 = 프로세스·파일 경계 밖.",
        40,
        50,
        1720,
        30,
        font=11,
    )

    # ── 사용자 · cli ──
    user = p.box("사용자\n(터미널 · CI)", 40, 110, 150, 60, "human", bold=True)
    cli = p.box(
        "cli 층 — cta generate / maintain / resolve 조립·입출력만 (판단 로직 없음)\ncli/generate.py run_generation: 재료 수집 → 엔진 선택 → 게이트 루프 → 제안",
        300,
        110,
        840,
        60,
        "cli",
        font=11,
    )
    p.edge(user, cli, "cta <명령>", pin(1, 0.5, 0, 0.5))

    # ── 작성 엔진 ──
    eng = p.lane(
        "작성 엔진 — run_writer(state) → WriterState 계약. 둘 중 하나가 돈다(ADR-0024 결정 7)",
        40,
        220,
        1100,
        470,
        "core",
        cid="engine",
    )
    p.edge(cli, eng, "run_writer 호출 (지침서·재료)", pin(0.25, 1, 0.25, 0))

    # legacy 서브그래프
    lg = p.lane(
        "legacy (기본) — core/writer_graph.py · LangGraph 서브그래프",
        20,
        40,
        440,
        410,
        "core",
        parent=eng,
        font=12,
        cid="legacy",
    )
    g_gather = p.box(
        "gather\n정보 수집 (inspect_target · query_code_graph)",
        50,
        50,
        190,
        44,
        "core",
        parent=lg,
        font=11,
    )
    g_write = p.box(
        "write\ngenerator 포트로 코드 생성 → write_test",
        50,
        120,
        190,
        44,
        "core",
        parent=lg,
        font=11,
    )
    g_run = p.box("run\nrun_tests (선택 실행만)", 20, 190, 190, 44, "core", parent=lg, font=11)
    g_quality = p.box(
        "quality\ncheck_quality → status=passed", 240, 190, 180, 44, "core", parent=lg, font=11
    )
    g_ask = p.box(
        "ask ⏸ interrupt\n사용자에게 계속/중지/힌트", 20, 290, 190, 44, "human", parent=lg, font=11
    )
    g_report = p.box(
        "report\n한계 보고 (정상 종료)", 240, 290, 180, 44, "state", parent=lg, font=11
    )
    p.vertex("LLM", 205, 112, 34, 16, LLM_BADGE, parent=lg)
    p.edge(g_gather, g_write, "", pin(0.5, 1, 0.5, 0), parent=lg)
    p.edge(g_write, g_run, "", pin(0.5, 1, 0.5, 0), parent=lg)
    p.edge(g_run, g_quality, "통과", pin(1, 0.5, 0, 0.5), parent=lg)
    p.edge(g_run, g_write, "실패", pin(0, 0.5, 0, 0.5), points=[(30, 212), (30, 142)], parent=lg)
    p.edge(g_run, g_ask, "같은 실패 반복 /\n4회마다", pin(0.5, 1, 0.5, 0), parent=lg)
    p.edge(g_run, g_report, "불가능 / 8회", pin(0.75, 1, 0.5, 0), parent=lg)
    p.edge(
        g_ask,
        g_write,
        "계속(+힌트)",
        pin(0, 0.5, 0, 0.75),
        points=[(12, 312), (12, 153)],
        parent=lg,
    )
    p.edge(g_ask, g_report, "중지", pin(1, 0.5, 0, 0.5), parent=lg)
    p.text(
        "노드 함수는 그래프 없이 단독 호출·테스트 가능. LLM은 generator 포트(llm/generation.py) 뒤에만 있다.",
        50,
        350,
        400,
        40,
        font=10,
        parent=lg,
    )

    # deep agent
    dp = p.lane(
        "deep (ADR-0024) — core/agent/ · Deep Agents 메인 test_lead + 서브에이전트 3",
        480,
        40,
        600,
        410,
        "core",
        parent=eng,
        font=12,
        cid="deep",
    )
    main = p.box(
        "메인 test_lead (prompts/test_lead.md)\n고유 도구: check_quality · report_finding\n+ ask_user(사람 개입, 고유 도구 아님)\n하네스 도구: write_todos · task(위임) · read_file/glob/grep",
        20,
        50,
        300,
        90,
        "core",
        parent=dp,
        font=11,
        align="left",
    )
    p.vertex("LLM", 270, 42, 34, 16, LLM_BADGE, parent=dp)
    mw = p.box(
        "미들웨어 (build.py)\nTodoListMiddleware · HideWriteTools(내장 쓰기 숨김)\nRunLedger: 시도 ≤8 · 4회마다 묻기 · 실패 분류(auto/ask/impossible)\nllm_middleware: 녹음/재생 · 토큰 합산(llm 층 인스턴스)",
        335,
        50,
        245,
        90,
        "core",
        parent=dp,
        font=10,
        align="left",
    )
    ex = p.box(
        "explorer (읽기 전용)\n탐색 — 형태·의존·생성법·유사 테스트\ninspect_target · query_code_graph",
        20,
        190,
        180,
        70,
        "core",
        parent=dp,
        font=10,
    )
    wr = p.box(
        "writer (쓰기·실행 유일)\n지침서+조사 보고로 작성·실행\nwrite_test · run_tests",
        210,
        190,
        180,
        70,
        "core",
        parent=dp,
        font=10,
    )
    dg = p.box(
        "diagnoser (읽기 전용)\n반복 실패 원인 → 수정 지시 / 사람 판단\ninspect_target · query_code_graph",
        400,
        190,
        180,
        70,
        "core",
        parent=dp,
        font=10,
    )
    for sub, xx in ((ex, 0.2), (wr, 0.5), (dg, 0.8)):
        p.edge(main, sub, "task", pin(xx, 1, 0.5, 0), parent=dp)
    p.edge(mw, main, "", pin(0, 0.5, 1, 0.5) + "dashed=1;", parent=dp)
    p.text(
        "FilesystemPermission: write 전 경로 deny — 파일을 바꾸는 길은 write_test뿐(ADR-0025 결정 2). "
        "general-purpose 서브는 빈 spec으로 무력화. 서브 모델은 메인 것을 물려받음. RECURSION_LIMIT 400. "
        "run_agent()가 결과를 WriterState 모양으로 돌려줘 게이트 루프·화면 출력은 두 엔진 공용.",
        20,
        280,
        560,
        60,
        font=10,
        parent=dp,
    )
    p.edge(
        lg,
        dp,
        "같은 도구 6개 · 같은 사람 개입 장치",
        pin(1, 0.12, 0, 0.12) + "dashed=1;endArrow=none;",
        parent=eng,
    )

    # ── 고유 도구 6개 ──
    tools = p.lane(
        "core/tools/ — 고유 도구 정확히 6개 (R4) · 1도구 1파일 · 문자열 반환 + 길이 상한(clip) · 예외 대신 문장",
        40,
        730,
        1100,
        100,
        "core",
        cid="tools",
    )
    names = [
        ("inspect_target\n대상 조사", "SourceInspector"),
        ("query_code_graph\n미리 정의된 쿼리만", "CodeGraph"),
        ("write_test\n테스트 폴더 밖 거부", "TestWriter"),
        ("run_tests\n빈 selector 거부(R5)", "TestRunner"),
        ("check_quality\nassert 수 비교", "QualityChecker"),
        ("report_finding\n한계 보고", "(포트 없음)"),
    ]
    tool_ids = []
    for i, (n, port) in enumerate(names):
        tool_ids.append(
            p.box(f"{n}\n→ {port}", 20 + i * 178, 40, 166, 48, "core", parent=tools, font=10)
        )
    p.edge(
        eng, tools, "도구 호출 (legacy 노드 · deep writer/explorer/diagnoser)", pin(0.5, 1, 0.5, 0)
    )

    # ── 포트 · 어댑터 · 실행 장치 ──
    ports = p.box(
        "core/ports.py — Protocol 포트 (Fake·실물이 상속 없이 구조적으로 들어맞는다)\nSourceInspector · CodeGraph · TestWriter · TestRunner · QualityChecker · UserGate · TestCodeGenerator · IntentClassifier · TestLocator",
        40,
        870,
        1100,
        50,
        "core",
        font=11,
    )
    p.edge(tools, ports, "", pin(0.5, 1, 0.5, 0))

    ad = p.lane(
        "adapters/java — 포트의 구체 구현 (Java · Maven · JUnit 5). core는 이 이름들을 모른다(R1)",
        40,
        960,
        700,
        100,
        "adapters",
        cid="adapters",
    )
    ad_mods = [
        "inspector.py\n대상 조사",
        "similar.py\n유사 테스트 검색",
        "writer.py + merge.py\n쓰기·컴파일 검사",
        "runner.py\n2단계(준비/오프라인)",
        "quality.py\nassert 수 비교",
        "skills/ SKILL.md\n작성 지식(ADR-0017)",
    ]
    for i, n in enumerate(ad_mods):
        p.box(n, 15 + i * 114, 40, 106, 48, "adapters", parent=ad, font=10)
    p.edge(ports, ad, "구현", pin(0.3, 1, 0.5, 0))

    gr = p.lane("graph 층 — 코드 그래프 (언어를 모른다)", 780, 960, 360, 100, "graph", cid="graph")
    p.box(
        "answers.py\nCodeGraph 구현 · 질의 → 답 문장", 15, 40, 160, 48, "graph", parent=gr, font=10
    )
    p.box(
        "store.py 인메모리 / neo4j_store.py\nDECLARES · CREATES · COVERS",
        185,
        40,
        160,
        48,
        "graph",
        parent=gr,
        font=10,
    )
    p.edge(ports, gr, "구현", pin(0.85, 1, 0.5, 0))

    sb = p.lane(
        "sandbox 층 — 실행 장치 (R6). 무엇을 실행하는지 모른다",
        40,
        1100,
        700,
        80,
        "sandbox",
        cid="sandbox",
    )
    p.box(
        "local_sandbox.py [기본]\n이 PC의 Maven·JDK", 15, 36, 210, 36, "sandbox", parent=sb, font=10
    )
    p.box(
        "docker_sandbox.py --runner docker\n네트워크 차단 · 마운트 통제",
        250,
        36,
        220,
        36,
        "sandbox",
        parent=sb,
        font=10,
    )
    p.box(
        "factory.py choose_runner\n명시 없으면 local · 폴백 없음",
        475,
        36,
        210,
        36,
        "sandbox",
        parent=sb,
        font=10,
    )
    p.edge(ad, sb, "runner → 명령 실행 위임", pin(0.5, 1, 0.5, 0))

    # 외부
    target = p.box(
        "대상 Maven 프로젝트 (src/main · src/test · pom.xml · git)\nadapters가 소스 읽기 · 테스트 파일 쓰기",
        40,
        1220,
        220,
        60,
        "ext",
        dashed=True,
        font=11,
    )
    jdk = p.box(
        "로컬 Maven · JDK 17+ (~/.m2)\n또는 Docker 컨테이너(격리)",
        300,
        1220,
        250,
        60,
        "ext",
        dashed=True,
        font=11,
    )
    neo = p.box("Neo4j (선택)\n없으면 파싱 폴백", 780, 1220, 200, 60, "ext", dashed=True, font=11)
    p.edge(
        ad,
        target,
        "",
        pin(0, 0.5, 0, 0.5) + "dashed=1;",
        points=[(20, 1010), (20, 1250)],
    )
    p.edge(sb, jdk, "mvn test (선택 실행만)", pin(0.55, 1, 0.5, 0) + "dashed=1;")
    p.edge(gr, neo, "bolt", pin(0.5, 1, 0.5, 0) + "dashed=1;")

    # ── llm 층 ──
    llm = p.lane(
        "llm 층 — LLM 호출의 유일한 통로 (R7). CI는 재생 모드, 카세트 없으면 실패(실호출 폴백 금지)",
        1180,
        220,
        580,
        300,
        "llm",
        cid="llm",
    )
    p.box(
        "config.py make_llm_client() · chat_model.py make_chat_model()\n클라이언트 생성의 유일한 입구 · .env(CTA_GATEWAY_URL/API_KEY/LLM_MODEL)",
        15,
        40,
        550,
        44,
        "llm",
        parent=llm,
        font=10,
    )
    p.box(
        "generation.py\nTestCodeGenerator\n(legacy write 노드)",
        15,
        100,
        170,
        60,
        "llm",
        parent=llm,
        font=10,
    )
    p.box(
        "AzureChatOpenAI 모델\n(deep 메인·서브가 공유)\n+ NoCallChatModel(재생 전용)",
        200,
        100,
        180,
        60,
        "llm",
        parent=llm,
        font=10,
    )
    p.box(
        "intent.py\nIntentClassifier\n(maintain 의도 분류)",
        395,
        100,
        170,
        60,
        "llm",
        parent=llm,
        font=10,
    )
    p.box(
        "replay.py 카세트 v1 · model_cassette.py 카세트 v2(미들웨어)\n요청 키 = deployment+시스템 프롬프트+메시지+도구 이름 · 완전 일치 · 폴백 없음",
        15,
        175,
        370,
        50,
        "llm",
        parent=llm,
        font=10,
    )
    p.box(
        "metering.py 토큰·예산\nmasking.py 시크릿 가림",
        395,
        175,
        170,
        50,
        "llm",
        parent=llm,
        font=10,
    )
    p.text(
        "prompts/*.md: system · write_test · write_test_append · classify_intent (코드 밖 데이터)",
        15,
        240,
        550,
        30,
        font=10,
        parent=llm,
    )
    gw = p.box(
        "사내 LLM 게이트웨이\nAzure OpenAI 호환 · deployment = 모델(gpt-5)\n주소·키는 환경변수/.env로만",
        1180,
        110,
        400,
        60,
        "ext",
        dashed=True,
        font=11,
    )
    p.edge(llm, gw, "HTTPS (실호출 시)", pin(0.5, 0, 0.5, 1) + "dashed=1;")
    p.edge(eng, llm, "생성 요청 / 모델 호출", pin(1, 0.2, 0, 0.2))

    # ── 안전장치 ──
    safe = p.lane(
        "안전장치 — 결정적, LLM 호출 없음 (R2). 테스트를 만든 에이전트는 판정에 관여하지 못한다",
        1180,
        560,
        580,
        400,
        "state",
        cid="safe",
    )
    p.box(
        "게이트 루프 core/submit.py generate_with_gates\nrun_writer → 게이트 → 탈락 사유를 지침서에 붙여 재생성 (max_retries 기본 3)\n소진 시 human_review(사람 확인) · 엔진 실패 시 not_passed",
        15,
        40,
        550,
        60,
        "core",
        parent=safe,
        font=10,
        align="left",
    )
    p.box(
        "게이트 6개 — core/gates.py 실행기 + adapters/java/gates.py·mutation.py·regression.py\n① AssertIntegrity(메서드 단위·허용 목록) ② SkipAnnotation ③ FileScope(허용 파일만)\n④ Coverage(JaCoCo 변경 라인 80% / 분기 70%, 회귀 금지) ⑤ Mutation(PIT 검출률) ⑥ BugReproduction(수정 전 코드에서 실패해야)\n--fast는 ④⑤ 생략. 애매하면 탈락 → 사람 확인(보수적)",
        15,
        115,
        550,
        80,
        "adapters",
        parent=safe,
        font=10,
        align="left",
    )
    p.box(
        "조치 결정 규칙표 core/pipeline/decide.py (maintain)\n(의도 × 기존 테스트 상태) → create_test / no_action / escalate / ask\nrefactor+실패 → escalate · unclear → ask · trivial → no_action. 기대값 자동 갱신 행 없음(R3)",
        15,
        210,
        550,
        60,
        "core",
        parent=safe,
        font=10,
        align="left",
    )
    p.box(
        "반복 상한 core/agent/limits.py RunLedger\n시도 ≤8(하드 캡) · 4회마다 묻기 · 같은 실패 2회 → ask · 시간 초과/실행 거부 → impossible",
        15,
        285,
        320,
        50,
        "core",
        parent=safe,
        font=10,
        align="left",
    )
    p.box(
        "사람 개입 core/user_gate.py\nInterruptUserGate: interrupt()로 정지 →\n터미널 질문 → 답으로 같은 지점 재개",
        350,
        285,
        215,
        50,
        "human",
        parent=safe,
        font=10,
    )
    p.text(
        "cta.toml [gates]·[retry]로 기준치·상한 조정 (core/config.py). 환경변수 > .env > cta.toml",
        15,
        345,
        550,
        30,
        font=10,
        parent=safe,
    )
    p.edge(
        cli, safe, "generate_with_gates", pin(0.98, 1, 0.05, 0), points=[(1160, 200), (1160, 540)]
    )
    p.edge(safe, eng, "run_writer(탈락 사유 포함 지침서)", pin(0, 0.2, 1, 0.7))
    p.edge(eng, safe, "ask ⏸ → interrupt", pin(1, 0.85, 0, 0.82) + "dashed=1;")

    # ── 상태 저장소 ──
    st = p.lane(
        ".cta/ 상태 저장소 — 생성물은 제안으로 보관, cta apply를 쳐야만 소스 반영(v4 Step 3)",
        1180,
        1000,
        580,
        90,
        "state",
        cid="state",
    )
    p.box(
        "proposals/ 제안\ncta diff → apply / discard", 15, 38, 170, 40, "state", parent=st, font=10
    )
    p.box(
        "escalations/ 사람 확인 항목\n종료 코드 3 → cta resolve",
        200,
        38,
        180,
        40,
        "state",
        parent=st,
        font=10,
    )
    p.box("memos/ 판단 메모\n다음 maintain 참고", 395, 38, 170, 40, "state", parent=st, font=10)
    p.edge(safe, st, "게이트 통과 → 제안 / 소진 → 사람 확인", pin(0.5, 1, 0.5, 0))
    p.edge(
        safe,
        user,
        "질문 ⏸ → 사용자 답 (ask_on_terminal)",
        pin(1, 0.1, 0.5, 0) + "dashed=1;",
        points=[(1790, 600), (1790, 95), (115, 95)],
    )

    # 범례
    lg_box = p.vertex(
        "범례",
        1180,
        1120,
        580,
        70,
        "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#666666;verticalAlign=top;fontStyle=1;fontSize=11;",
        "1",
    )
    items = [
        ("cli", "cli 층"),
        ("core", "core 층"),
        ("adapters", "adapters/java"),
        ("llm", "llm 층(LLM 호출)"),
        ("graph", "graph"),
        ("sandbox", "sandbox"),
        ("human", "사람 개입"),
        ("state", ".cta 상태/안전장치 틀"),
        ("ext", "외부(점선)"),
    ]
    for i, (k, n) in enumerate(items):
        col, row = divmod(i, 2)
        f, s = C[k]
        p.vertex(
            "",
            10 + col * 115,
            26 + row * 20,
            22,
            12,
            f"rounded=0;html=1;fillColor={f};strokeColor={s};"
            + ("dashed=1;" if k == "ext" else ""),
            parent=lg_box,
        )
        p.vertex(
            n,
            36 + col * 115,
            20 + row * 20,
            80,
            22,
            "text;html=1;align=left;verticalAlign=middle;fontSize=10;",
            parent=lg_box,
        )
    return p


# ═══════════════════════════════════════════════════════════════════════
# 페이지 2 — CLI 명령별 흐름
# ═══════════════════════════════════════════════════════════════════════
def page_cli() -> Page:
    p = Page("2. CLI 명령별 흐름")
    p.text(
        "Code Test Agent (cta) — CLI 명령별 흐름",
        40,
        20,
        900,
        30,
        font=22,
        bold=True,
        color="#1e1e1e",
    )
    p.text(
        "종료 코드: 0 정상 · 3 사람 확인 필요(실패 아님) · 2 품질 미달 · 1 오류. 빨간 LLM 배지가 붙은 단계만 LLM을 호출한다(llm 층 경유, 녹음·재생 가능). "
        "색 = 층(cli 파랑 · core 초록 · adapters 노랑 · llm 빨강 · graph 보라 · .cta 회색).",
        40,
        52,
        1700,
        40,
        font=11,
    )
    pool = p.vertex(
        "cta 명령",
        40,
        100,
        1740,
        1120,
        "swimlane;html=1;childLayout=stackLayout;horizontal=1;startSize=30;horizontalStack=0;resizeParent=1;resizeParentMax=0;collapsible=0;fontStyle=1;fontSize=13;",
        "1",
    )
    LANE = "swimlane;html=1;startSize=40;horizontal=0;collapsible=0;fillColor=none;fontSize=12;fontStyle=1;whiteSpace=wrap;"

    def lane(name, y, h):
        return p.vertex(name, 0, y, 1740, h, LANE, parent=pool)

    def flow(lane_id, steps, y=40, x0=60, gap=70, h=80):
        """steps: (label, key, w, llm)."""
        ids, x = [], x0
        for label, key, w, llm in steps:
            if key == "start":
                cid = p.ellipse(label, x, y, w, h, "cli", parent=lane_id, font=11)
            elif key == "end":
                cid = p.ellipse(
                    label, x, y, w, h, "core" if "0" in label else "state", parent=lane_id, font=11
                )
            else:
                cid = p.box(label, x, y, w, h, key, parent=lane_id, font=10)
            if llm:
                p.vertex("LLM", x + w - 36, y - 8, 34, 16, LLM_BADGE, parent=lane_id)
            ids.append((cid, x, w))
            x += w + gap
        for (a, _, _), (b, _, _) in zip(ids, ids[1:], strict=False):
            p.edge(a, b, "", pin(1, 0.5, 0, 0.5), parent=lane_id)
        return [i[0] for i in ids]

    # A. generate
    la = lane(
        "A. cta generate",
        30,
        200,
    )
    flow(
        la,
        [
            (
                "cta generate <파일명> | --class C\n[--max-methods N] [--engine deep] [--fast]",
                "start",
                150,
                False,
            ),
            (
                "[1/4] 재료 수집 adapters/materials.py\n테스트 없는 메서드 선정 · 확인 항목(분기·경계·예외·null) · 기존 테스트 파일",
                "adapters",
                250,
                False,
            ),
            ("[2/4] 객체 생성법 확인\n직접 생성 / builder / mock", "adapters", 170, False),
            (
                "[3/4] 작성 엔진 (페이지 1)\nlegacy writer_graph | deep core/agent\n쓰기→실행→진단 반복 ≤8회, ⏸ 4회마다 질문",
                "core",
                270,
                True,
            ),
            (
                "[4/4] 게이트 ①~⑥ (결정적)\ncore/submit.py 탈락 사유 → 재생성 ≤3회\n--fast: ④커버리지 ⑤뮤테이션 생략",
                "core",
                250,
                False,
            ),
            (".cta/proposals\n제안 저장 (소스 미반영)", "state", 160, False),
            ("종료 0\ncta diff로 검토", "end", 110, False),
        ],
    )
    p.text(
        "게이트 재시도 소진 → 사람 확인(종료 3) · 품질 미달(종료 2). --engine deep: --record 파일 / --replay 파일 로 LLM 호출 녹음·재생(기록과 어긋나면 실패, 실호출 폴백 없음). 실행은 sandbox(local 기본 / docker)에서 선택한 테스트만 돈다(R5).",
        60,
        135,
        1600,
        40,
        font=10,
        parent=la,
    )

    # B. maintain
    lb = lane("B. cta maintain", 230, 300)
    b = flow(
        lb,
        [
            ("cta maintain --diff HEAD~1\n[--plan-only] [--intent 의도]", "start", 150, False),
            (
                "변경 추출 adapters/changes.py\ngit diff → 변경 심볼 + 단서\n(시그니처·접근 제어자·주석만·커밋 메시지·이슈) · 수정 전 소스",
                "adapters",
                240,
                False,
            ),
            (
                "건별 의도 분류 llm/intent.py\nbug_fix / refactor / new_feature / trivial / unclear\n+ 확신도·근거·분석. 실패 → unclear · --intent면 확정",
                "llm",
                240,
                True,
            ),
            (
                "기존 테스트 찾기 + 검증 실행\nTestLocator(그래프 COVERS 실측 → 참조 파싱 폴백)\n선택 실행만(R5) → pass / fail / none",
                "adapters",
                230,
                False,
            ),
        ],
        gap=60,
    )
    dec = p.rhombus(
        "규칙표\ncore/pipeline/decide.py\n의도 × 테스트 상태\n(LLM 없음, R2)",
        1150,
        30,
        180,
        100,
        parent=lb,
        font=10,
    )
    p.edge(b[-1], dec, "", pin(1, 0.5, 0, 0.5), parent=lb)
    b_create = p.box(
        "bug_fix · new_feature → create_test → A의 [3/4]~[4/4] 경로\nbug_fix: 재발 방지 테스트(⑥회귀 게이트: 수정 전 코드에서 실패해야)\nnew_feature: 기능 테스트 → 제안",
        1390,
        50,
        320,
        60,
        "core",
        parent=lb,
        font=10,
    )
    b_none = p.box(
        "no_action\nrefactor+통과(동작 보존 확인) · trivial(주석·공백만)",
        1390,
        115,
        320,
        40,
        "state",
        parent=lb,
        font=10,
    )
    b_esc = p.box(
        "escalate / ask → .cta/escalations 저장 후 멈춤 (종료 3)\nrefactor+실패: 기대값을 고치지 않고 실패 내용·의심 위치만 정리(R3)\nunclear / refactor+테스트 없음: 사람에게 묻기",
        1390,
        170,
        320,
        60,
        "human",
        parent=lb,
        font=10,
    )
    p.edge(dec, b_create, "", pin(1, 0.5, 0, 0.5), parent=lb)
    p.edge(
        dec, b_none, "refactor+pass · trivial", pin(0.5, 1, 0, 0.5), points=[(1240, 135)], parent=lb
    )
    p.edge(
        dec, b_esc, "refactor+fail · unclear", pin(0.5, 1, 0, 0.5), points=[(1240, 200)], parent=lb
    )
    p.text(
        "화면에는 변경 건마다 ①의도 판단 ②조치 블록(판단·확신도·근거·할 일)을 적는다(ADR-0015 D2). 확신도는 표시용이며 코드는 이 값으로 분기하지 않는다. --plan-only는 규칙표까지만. 판단 메모(.cta/memos)에 비슷한 결정이 있으면 참고로 보여 준다. 사람 확인이 하나라도 있으면 종료 3.",
        60,
        235,
        1600,
        50,
        font=10,
        parent=lb,
    )

    # C. resolve
    lc = lane(
        "C. cta resolve",
        530,
        200,
    )
    flow(
        lc,
        [
            (
                "cta resolve <id> --intended |\n--test-issue | --proceed | --as | --skip",
                "start",
                150,
                False,
            ),
            (
                "저장된 사람 확인 항목 읽기\n.cta/escalations/<id>.json\n재개 지점 = 테스트 작성 단계 진입(ADR-0015 D3)",
                "state",
                250,
                False,
            ),
            (
                "사람 결정 → 지침·허용 목록 cli/resolve_cmd.py\n--intended: 실패 테스트 기대값을 새 동작 기준으로\n--test-issue: 테스트를 동작 기준으로 재작성\n--as 의도: 규칙표부터 다시(LLM 없음) · --skip: 기록만",
                "cli",
                300,
                False,
            ),
            (
                "A의 [3/4]~[4/4] 경로로 재개\n허용 목록 = 실패한 테스트 메서드만 assert 변경 허용\n나머지는 ①AssertIntegrity 게이트가 보호",
                "core",
                280,
                True,
            ),
            (".cta/proposals 제안\n+ .cta/memos 판단 메모", "state", 170, False),
            ("종료 0 / 2 / 3", "end", 110, False),
        ],
    )
    p.text(
        "사람이 명시적으로 고른 선택지만 실행한다 — R3는 '사람 확인 없는' 기대값 갱신을 막는 규칙이다. 판단 메모는 다음 maintain에서 키워드 검색으로 참고 자료가 된다.",
        60,
        135,
        1600,
        40,
        font=10,
        parent=lc,
    )

    # D. diff / apply / discard
    ld = lane("D. cta diff\napply · discard", 730, 150)
    flow(
        ld,
        [
            ("cta diff [이름]", "start", 120, False),
            (
                ".cta/proposals 읽기 cli/proposals.py\n제안 내용을 diff 형식으로 출력",
                "state",
                250,
                False,
            ),
            ("사람 검토", "human", 130, False),
            (
                "cta apply [이름|--all]\n테스트 트리(src/test)에 쓰기 — 이때만 소스 반영",
                "cli",
                280,
                False,
            ),
            ("종료 0", "end", 100, False),
        ],
        y=35,
    )
    p.box("cta discard → 제안 폐기 (소스 무변경)", 1360, 35, 250, 40, "state", parent=ld, font=10)
    p.text(
        "생성물은 apply 전까지 소스에 반영되지 않는다(v4 Step 3). CI에서는 종료 코드로 분기(사용가이드 §13).",
        60,
        120,
        1200,
        30,
        font=10,
        parent=ld,
    )

    # E. graph / eval / demo
    le = lane("E. cta graph\neval · demo", 880, 240)
    flow(
        le,
        [
            ("cta graph [--coverage]", "start", 130, False),
            (
                "Java 소스 파싱 adapters/graph_builder.py\n클래스·메서드·테스트 노드 · DECLARES · CREATES",
                "adapters",
                270,
                False,
            ),
            (
                "JaCoCo 실측 adapters/coverage.py\n테스트 → 메서드 COVERS 엣지 (--coverage)",
                "adapters",
                250,
                False,
            ),
            (
                "graph/neo4j_store.py 적재\n(접속 실패 → 파싱 폴백, graph_access.py)",
                "graph",
                250,
                False,
            ),
            (
                'query_code_graph 도구 · TestLocator\n"기존 테스트 찾기"가 실측 기준이 된다',
                "core",
                250,
                False,
            ),
            ("종료 0 / 1", "end", 100, False),
        ],
        y=35,
    )
    p.box(
        "cta eval [--intents] — 골든 케이스·의도 세트로 분류 정확도·unclear 비율 실측 (cli/eval_cmd.py · eval_intents.py)",
        60,
        140,
        640,
        40,
        "cli",
        parent=le,
        font=10,
    )
    p.box(
        "cta demo — 저장된 LLM 호출 기록(카세트)으로 대표 시나리오 SC-001~004 재생, 비용 0 (cli/demo_cmd.py)",
        730,
        140,
        640,
        40,
        "cli",
        parent=le,
        font=10,
    )
    p.text(
        '공통 옵션: --non-interactive(질문 없이) · --quiet · --project(생략 시 cli/locate.py가 현재→상위→하위 폴더에서 pom.xml 탐색). 오류는 cli/hints.py가 "왜 / 할 일 / 명령" 세 줄로 안내.',
        60,
        190,
        1600,
        40,
        font=10,
        parent=le,
    )
    return p


def main() -> None:
    out = Path(sys.argv[1])
    pages = [page_agent(), page_cli()]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<mxfile host="drawio" version="26.0.0" type="device">'
        + "".join(pg.xml() for pg in pages)
        + "</mxfile>\n"
    )
    out.write_text(xml, encoding="utf-8")
    print(f"wrote {out} ({sum(len(pg.cells) for pg in pages)} cells, {len(pages)} pages)")


if __name__ == "__main__":
    main()
