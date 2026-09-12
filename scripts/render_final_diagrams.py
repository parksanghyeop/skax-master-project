"""최종산출물/cta-diagrams.drawio — 현재 프로젝트 기준 그림 4장(4페이지)을 생성한다.

1. Agent Architecture (인포그래픽)   — render_final_infographic.page_architecture_v2
2. Detailed Architecture (상세 설명)  — render_drawio.page_agent + 오늘 수정 반영(같은 이름 교체·제안 이어붙임)
3. User Command Flows (명령어별 흐름) — render_drawio.page_cli + 오늘 수정 반영
4. Graph DB Architecture (인포그래픽) — 이 파일에서 새로 그린다: 노드 2종·엣지 4종, 채우는 쪽(파싱·JaCoCo·CALLS 추정),
   질의 4종과 소비처(도구·TestLocator·ImpactFinder), Neo4j 없을 때의 폴백, 샌드박스 밖 배치·단일 라벨 설계.
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
    GRAY,
    GREEN,
    INK,
    PURPLE,
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


def main() -> None:
    out = Path(sys.argv[1])
    p1 = page_architecture_v2()
    p1.name = "1. Agent Architecture"
    pages = [p1, page_detail(), page_flows(), page_graphdb()]
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
