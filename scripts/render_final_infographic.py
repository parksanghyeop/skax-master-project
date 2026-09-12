"""최종산출물용 인포그래픽 draw.io 문서(최종산출물/architecture-infographic.drawio)를 생성한다.

docs/architecture-infographic.drawio(과거 판, 더 이상 갱신하지 않음)의 부품(아이콘·카드·칩)을
그대로 빌려 ADR-0026 이후의 구조를 그린다.
페이지 1 "Agent Architecture": 기존 그림 + 판단 메모(임베딩 검색) 카드, 코드 그래프에 호출 관계(추정).
페이지 2 "Agent Workflow": 기존 흐름 + ① 변경 추출 아래 "영향 범위", ② 의도 판단 아래 "판단 메모 참고".
페이지 3 "Impact & Memory": 영향 범위(코드 그래프 CALLS → 호출자 → 화면·지침서·--impact)와
판단 메모(사람 판단 → 상황 요약 → 임베딩 → 저장 → 하이브리드 검색 → 참고) 두 줄.
외부 서비스·이미지 파일 의존 없음.

사용:  python scripts/render_final_infographic.py 최종산출물/architecture-infographic.drawio
"""

# ruff: noqa: E501 — 그림 좌표·문구 줄은 100자 규칙을 적용하지 않는다

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_drawio_infographic import (  # noqa: E402
    AMBER,
    BLUE,
    GRAY,
    GREEN,
    ICONS,
    INK,
    PINK,
    PURPLE,
    RED,
    Page,
    page_architecture,
    page_workflow,
    pin,
)

# 새 아이콘 2개 — 호출 관계(사슬), 임베딩 벡터(점 → 화살표)
ICONS["link"] = (
    '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.5 1.5"/>'
    '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.5-1.5"/>'
)
ICONS["vector"] = (
    '<circle cx="5" cy="18" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="14" cy="15" r="1.5"/>'
    '<path d="M5 18L20 4M16 4h4v4"/>'
)


def page_architecture_v2() -> Page:
    """페이지 1 — 기존 그림에 판단 메모 카드와 그래프 부제를 더한다."""
    p = page_architecture()
    memo = p.card(
        40,
        600,
        130,
        120,
        "vector",
        "판단 메모",
        "이름 일치 + 임베딩 검색",
        PINK,
        icon_size=34,
        title_size=14,
    )
    p.edge("agent", memo, "비슷한 과거 판단 (참고)", pin(0.02, 1, 0.5, 0) + "dashed=1;")
    # 코드 그래프 카드의 부제를 바꾼다 — 생성된 셀 문자열에서 찾아 치환(카드는 문자열로만 남아 있다)
    p.cells = [
        c.replace("Neo4j (선택)", "확정 3종 + 호출 관계(추정)") if "Neo4j (선택)" in c else c
        for c in p.cells
    ]
    p.cells = [
        c.replace("Azure OpenAI 호환", "chat + 임베딩") if "Azure OpenAI 호환" in c else c
        for c in p.cells
    ]
    p.cells = [
        c.replace('value="기존 테스트 찾기"', 'value="기존 테스트 · 영향 범위"') for c in p.cells
    ]
    p.text(
        "<b>ADR-0026</b> — 영향 범위(누가 호출하나)는 코드 그래프가, 비슷한 과거 판단은 임베딩이 찾는다. 둘 다 규칙표에는 못 들어간다.",
        240,
        790,
        1000,
        24,
        font=13,
        color=INK,
    )
    return p


def page_workflow_v2() -> Page:
    """페이지 2 — ①·② 아래에 영향 범위·판단 메모 칩을 단다."""
    p = page_workflow()
    Y = 150  # page_workflow의 단계 줄 y
    # page_workflow가 만든 단계 카드 id는 생성 순서로 v1(제목 텍스트)… — 카드 id를 문자열에서 찾는다
    step_ids = [
        c.split('id="')[1].split('"')[0]
        for c in p.cells
        if "container=1" in c and "arcSize=12" in c
    ]
    impact = p.chip(40, Y + 210, 250, "link", "영향 범위: 호출하는 곳 (추정)", PURPLE, font=11)
    p.chip(40, Y + 250, 250, "list", "→ 화면 · 지침서 · --impact 파생 건", PURPLE, font=11)
    memo = p.chip(40, Y + 310, 250, "vector", "판단 메모 참고 (이름 일치 + 임베딩)", PINK, font=11)
    p.edge(step_ids[0], impact, "", pin(0.5, 1, 0.5, 0) + "dashed=1;")
    p.edge(step_ids[1], memo, "", pin(0.2, 1, 1, 0.5) + "dashed=1;", points=[(292, Y + 327)])
    return p


def page_impact() -> Page:
    p = Page("Impact & Memory")
    p.text("Code Test Agent — Impact & Memory", 40, 20, 900, 34, font=26, color=INK, bold=True)
    p.text(
        "ADR-0026: 코드 RAG는 벡터가 아니라 그래프 — 구조 질의는 코드 그래프(정답), 자연어 검색은 임베딩(보조)",
        40,
        58,
        1100,
        24,
        font=14,
    )

    W, H, GAP = 170, 130, 50

    def row(zone_id, items, y=60):
        ids = []
        for i, (icon, title, sub, color, llm) in enumerate(items):
            x = 30 + i * (W + GAP)
            cid = p.card(
                x, y, W, H, icon, title, sub, color, parent=zone_id, icon_size=38, title_size=14
            )
            if llm:
                p.llm_tag(x + W - 48, y - 8, parent=zone_id)
            ids.append(cid)
        for a, b in zip(ids, ids[1:], strict=False):
            p.edge(a, b, "", pin(1, 0.5, 0, 0.5), parent=zone_id)
        return ids

    # ── 1. 영향 범위 ──
    za = p.zone(
        40,
        110,
        1400,
        300,
        "영향 범위 — 코드 그래프가 답한다 (호출 관계는 추정, 확신도를 붙인다)",
        PURPLE,
        cid="za",
    )
    row(
        za,
        [
            ("git", "변경된 메서드", "git diff → Class#method", AMBER, False),
            ("link", "호출 관계 추정", "정규식 · high / medium · 없으면 안 만든다", PURPLE, False),
            ("db", "코드 그래프", "선언·생성·실측 커버·호출(추정)", PURPLE, False),
            ("list", "호출자 목록", "확신 높은 순 · 호출 줄 발췌", PURPLE, False),
            ("pen", "호출자 경유 테스트", "지침서 + --impact 파생 건", GREEN, True),
        ],
    )
    p.chip(30, 215, 330, "eye", "화면: 영향 범위 줄 · ↳ 파생 건 표시", GRAY, parent=za, font=11)
    p.chip(
        380,
        215,
        330,
        "table",
        "규칙표에는 넣지 않는다 (추정은 안전장치 입력이 될 수 없다)",
        GRAY,
        parent=za,
        font=11,
    )
    p.chip(
        730, 215, 330, "shield", "폴백: 그래프 DB 없어도 그 자리에서 파싱", GRAY, parent=za, font=11
    )
    p.text(
        '예: OrderService.findById를 고치면 → 호출자 OrderController.get · OrderService.pay · cancel · updateAmount [high] → "호출자를 거쳐 변경된 동작이 드러나는 시나리오"를 시험한다',
        30,
        262,
        1340,
        24,
        font=12,
        parent=za,
    )

    # ── 2. 판단 메모 ──
    zb = p.zone(
        40,
        450,
        1400,
        300,
        "판단 메모 — 임베딩은 자연어에만 (참고일 뿐, 규칙표를 우회하지 못한다)",
        PINK,
        cid="zb",
    )
    row(
        zb,
        [
            ("user", "사람 판단", "cta resolve", PINK, False),
            ("list", "상황 요약", "커밋 메시지 + 대상 + 분석", PINK, False),
            ("vector", "임베딩", "text-embedding-3-small", RED, True),
            ("folder", "메모 저장", ".cta/memos (상황 + 벡터)", GRAY, False),
            ("search", "다음 maintain 검색", "이름 일치 → 코사인 · 최대 3건", BLUE, False),
            ("chip", "의도 판단에 참고", "프롬프트 [과거 판단 사례]", RED, True),
        ],
    )
    p.chip(
        30,
        215,
        330,
        "shield",
        "게이트웨이 없으면 이름 일치만 (그대로 동작)",
        GRAY,
        parent=zb,
        font=11,
    )
    p.chip(
        380,
        215,
        330,
        "table",
        "규칙표는 메모를 받지 않는다 (불변식 테스트)",
        GRAY,
        parent=zb,
        font=11,
    )
    p.chip(730, 215, 330, "code", "코드·diff는 임베딩하지 않는다", GRAY, parent=zb, font=11)
    p.text(
        '예: 과거 "fix: 간헐적 실패 수정 / RetryPolicy.backoff" ← 새 변경 "chore: flaky 테스트 대응 / OrderService.pay" — 이름은 달라도 상황이 닮아 찾는다',
        30,
        262,
        1340,
        24,
        font=12,
        parent=zb,
    )

    # ── 하단: 하지 않는 것 ──
    p.text(
        "<b>하지 않는 것</b> — 코드 본문을 임베딩해 벡터 유사도로 영향 범위 찾기(닮은 코드 ≠ 부르는 코드) · 벡터 DB 의존성 · 호출 관계를 규칙표 입력으로 · 깊이 2 이상 전이 영향",
        40,
        780,
        1400,
        24,
        font=13,
        color=INK,
    )
    return p


def main() -> None:
    out = Path(sys.argv[1])
    pages = [page_architecture_v2(), page_workflow_v2(), page_impact()]
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
