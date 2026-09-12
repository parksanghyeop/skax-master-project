"""판단 메모 — 사람이 resolve로 내린 결정을 기록하고, 다음 변경 대응에서 참고로 보여준다.

시나리오 SC-002 3단계 "비슷한 과거 변경 사례를 찾아 참고 자료로 같이 보여주고".
검색은 하이브리드다(ADR-0026 D3): 같은 클래스·메서드 이름 일치(결정적)를 먼저, 그 다음
상황 요약(자연어)의 임베딩 코사인 유사도로 채운다 — "이름은 다른데 상황이 같은" 과거 판단을
찾기 위해(v4 4.1 ④·4.2). 임베딩이 없으면(게이트웨이 미설정·구 메모) 이름 일치만 동작한다.
**참고일 뿐 규칙표를 우회하지 못한다**(v4 4.2). 층: cli.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from cta.adapters.java.maven import MavenProject
from cta.llm.embeddings import cosine

MEMOS_DIR = ".cta/memos"
MAX_SHOWN = 3  # 참고 사례는 많아야 3건 — 화면·프롬프트 모두
# 이 값 아래는 "닮지 않은 상황"으로 보고 붙이지 않는다 — text-embedding-3-small에서 무관한 글끼리는
# 대체로 0.1~0.3, 같은 뜻의 다른 표현은 0.5 이상이라는 경험칙. 실사용 메모로 조정한다(ADR-0026 D3)
SIMILARITY_MIN = 0.35


@dataclass(frozen=True)
class Memo:
    """판단 메모 한 건 — 어떤 대상에 대해 사람이 무엇을 왜 결정했나."""

    target: str  # "Class#method"
    category: str  # 그때의 의도 분류
    decision: str  # 사람의 결정 (intended / test-issue / proceed / skip)
    note: str  # 한 줄 설명
    created_at: str
    # 아래 둘은 ADR-0026 D3에서 추가 — 구 메모 파일에는 없으므로 기본값으로 읽힌다
    situation: str = ""  # 그때의 상황 요약(자연어: 커밋 메시지 첫 줄 + 대상 + 분석) — 임베딩 원문
    embedding: list[float] | None = None  # situation의 벡터. 없으면 이름 일치 검색에만 참여


def _dir(project: MavenProject) -> Path:
    return project.root / MEMOS_DIR


def save_memo(project: MavenProject, memo: Memo) -> Path:
    d = _dir(project)
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    # 같은 시각에 두 번 저장되면(Windows 시계 해상도 ~15ms) 파일이 덮어써져 메모가 사라진다 —
    # 같은 자리 수의 순번을 붙여 이름을 구분하고, 이름순 정렬(list_memos)이 저장 순서와 같게 한다
    seq = 0
    path = d / f"{stamp}-{seq:02d}.json"
    while path.exists():
        seq += 1
        path = d / f"{stamp}-{seq:02d}.json"
    path.write_text(json.dumps(asdict(memo), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_memos(project: MavenProject) -> list[Memo]:
    d = _dir(project)
    if not d.is_dir():
        return []
    return [Memo(**json.loads(p.read_text(encoding="utf-8"))) for p in sorted(d.glob("*.json"))]


def situation_text(commit_message: str, target: str, analysis: str = "") -> str:
    """임베딩할 상황 요약 — 자연어만 담는다(커밋 메시지 첫 줄 + 대상 + 있으면 분석).

    diff·코드는 넣지 않는다: 임베딩 검색은 자연어 두 곳(커밋 메시지·판단 메모)에만 쓴다(v4 4.1 ④).
    저장 시(resolve)와 검색 시(maintain)가 같은 함수를 써야 벡터가 같은 공간에 놓인다.
    """
    first_line = commit_message.strip().splitlines()[0] if commit_message.strip() else ""
    parts = [f"변경 대상 {target.replace('#', '.')}"]
    if first_line:
        parts.insert(0, f"커밋 메시지: {first_line}")
    if analysis.strip():
        parts.append(f"분석: {analysis.strip()}")
    return " / ".join(parts)


def find_similar(
    project: MavenProject, target: str, query_vector: list[float] | None = None
) -> list[Memo]:
    """비슷한 과거 판단 최대 MAX_SHOWN건 — 이름 일치(같은 메서드 → 같은 클래스, 최근순)를 먼저,
    빈 자리는 query_vector와 코사인 유사도가 SIMILARITY_MIN 이상인 메모로 높은 순서대로 채운다.

    query_vector가 없으면(게이트웨이 미설정) 이름 일치만 — 예전 동작 그대로.
    """
    class_name = target.split("#", 1)[0]
    memos = list_memos(project)
    same_method = [m for m in memos if m.target == target]
    same_class = [m for m in memos if m.target != target and m.target.startswith(class_name + "#")]
    picked = (list(reversed(same_method)) + list(reversed(same_class)))[:MAX_SHOWN]
    if query_vector is None or len(picked) >= MAX_SHOWN:
        return picked
    # 흐름: 이름으로 못 찾은 메모 중 벡터가 있는 것만 → 코사인 계산 → 기준치 이상을 높은 순으로 채움
    rest = [m for m in memos if m not in picked and m.embedding]
    scored = sorted(((cosine(query_vector, m.embedding), m) for m in rest), key=lambda s: -s[0])
    for score, memo in scored:
        if score < SIMILARITY_MIN or len(picked) >= MAX_SHOWN:
            break
        picked.append(memo)
    return picked


def render_memos(memos: list[Memo]) -> str:
    """ "참고" 줄에 들어갈 문자열. 없으면 빈 값(호출부가 '없음'을 찍는다)."""
    if not memos:
        return ""
    parts = [
        f"{m.created_at[:10]} {m.target.replace('#', '.')}: {m.category} → {m.decision} ({m.note})"
        for m in memos
    ]
    return " / ".join(parts)
