"""스킬 읽기·선택·렌더링 — 재료 수집 결과(신호)로 어떤 지식 묶음을 프롬프트에 실을지 정한다.

ADR-0017. 왜 규칙 기반인가(R2·재생): 선택이 결정적이어야 같은 입력에 같은 프롬프트가 나오고
저장된 호출 기록으로 재생이 된다. 모델이 스킬을 스스로 고르는 도구는 만들지 않는다(R4).
왜 adapters/java에 있나(R1): 스킬 본문과 선택 신호(mock 판정·재발 방지 게이트)는 Java 어댑터의
개념이다. 스킬은 "어떻게 잘 쓰나"만 담는다 — 게이트·규칙표가 정한 "무엇을 해도 되나"는 바꾸지
못한다(테스트로 고정). 층: adapters.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cta.adapters.java.materials import Materials

SKILLS_DIR = Path(__file__).parent
SKILL_FILE = "SKILL.md"

# 스킬 이름 — 폴더 이름과 같다. 선택 규칙표의 키이자 화면·산출물에 찍히는 식별자.
SKILL_JUNIT5_MOCKITO = "junit5-mockito"
SKILL_REGRESSION_TEST = "regression-test"

# 재료 수집(materials.py)이 의존 객체를 mock으로 판정했을 때의 strategy 문구 — 그쪽과 한 쌍이다.
_MOCK_STRATEGY = "mock 사용"


@dataclass(frozen=True)
class Skill:
    """SKILL.md 한 개. frontmatter(name·description·when) + 본문."""

    name: str
    description: str
    when: str
    body: str


@dataclass(frozen=True)
class SkillSignals:
    """선택 규칙표의 입력 — 전부 이미 결정돼 있는 값에서 나온다(LLM 없음).

    uses_mock: 재료 수집이 "mock 사용"으로 판정한 의존 객체가 있다.
    regression: 버그 수정 → 테스트 추가 실행(게이트 regression이 붙는다).
    resume_with_authorized: resolve 재개 — 사람이 고쳐도 된다고 지정한 테스트가 있다.
    """

    uses_mock: bool = False
    regression: bool = False
    resume_with_authorized: bool = False


# 선택 규칙표: 스킬 이름 → 신호 조건. 행을 추가하면 스킬이 하나 늘어난다.
_RULES: dict[str, Callable[[SkillSignals], bool]] = {
    SKILL_JUNIT5_MOCKITO: lambda s: s.uses_mock,
    SKILL_REGRESSION_TEST: lambda s: s.regression,
}


def parse_skill(text: str, fallback_name: str = "") -> Skill:
    """SKILL.md 문자열을 Skill로. frontmatter는 `---`로 감싼 `key: value` 줄들이다.

    실패 시 동작: frontmatter가 없으면 전체를 본문으로 보고 이름은 폴더 이름(fallback_name).
    """
    meta: dict[str, str] = {}
    body = text
    stripped = text.lstrip()
    if stripped.startswith("---"):
        _, _, rest = stripped.partition("---")
        header, sep, body = rest.partition("\n---")
        if sep:
            for line in header.splitlines():
                key, colon, value = line.partition(":")
                if colon:
                    meta[key.strip()] = value.strip()
        else:
            body = text
    return Skill(
        name=meta.get("name", fallback_name),
        description=meta.get("description", ""),
        when=meta.get("when", ""),
        body=body.strip(),
    )


def load_skills(root: Path = SKILLS_DIR) -> dict[str, Skill]:
    """root 아래 `<이름>/SKILL.md`를 전부 읽는다. 폴더 이름순."""
    skills: dict[str, Skill] = {}
    for path in sorted(root.glob(f"*/{SKILL_FILE}")):
        skill = parse_skill(path.read_text(encoding="utf-8"), fallback_name=path.parent.name)
        skills[skill.name] = skill
    return skills


def signals_from(
    materials: Materials,
    regression_sources: dict | None,
    authorized_tests: set[str] | None,
) -> SkillSignals:
    """run_generation이 이미 들고 있는 값에서 신호를 뽑는다 — 새 판단은 없다."""
    return SkillSignals(
        uses_mock=any(c.strategy == _MOCK_STRATEGY for c in materials.constructions),
        regression=regression_sources is not None,
        resume_with_authorized=bool(authorized_tests),
    )


def select_skills(signals: SkillSignals, skills: dict[str, Skill] | None = None) -> list[Skill]:
    """규칙표에 걸리는 스킬을 규칙표 순서대로. 파일이 없는 이름은 조용히 건너뛰지 않고 KeyError."""
    available = load_skills() if skills is None else skills
    return [available[name] for name, matches in _RULES.items() if matches(signals)]


def render_skills(selected: list[Skill]) -> str:
    """프롬프트 [프로젝트 관례] 자리에 붙일 문자열. 없으면 빈 값."""
    return "\n\n".join(f"[스킬: {s.name} — {s.description}]\n{s.body}" for s in selected)
