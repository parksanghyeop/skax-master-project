"""테스트 작성 스킬(adapters/java/skills) — 읽기·규칙 선택·렌더링·불변식 (ADR-0017)."""

from pathlib import Path

from cta.adapters.java.materials import ConstructionHint, Materials
from cta.adapters.java.skills.select import (
    SKILL_JUNIT5_MOCKITO,
    SKILL_REGRESSION_TEST,
    SKILLS_DIR,
    Skill,
    SkillSignals,
    load_skills,
    parse_skill,
    render_skills,
    select_skills,
    signals_from,
)


def _materials(constructions: list[ConstructionHint]) -> Materials:
    return Materials(
        "OrderService", "com.example", Path("OrderService.java"), [], [], constructions
    )


MOCK = ConstructionHint("OrderRepository", "mock 사용", "DB에 접근하는 인터페이스")
VALUE = ConstructionHint("Order", "직접 생성", "Order.builder() 사용")


class TestLoad:
    def test_리포의_스킬_두_개를_frontmatter와_함께_읽는다(self):
        skills = load_skills()
        assert set(skills) == {SKILL_JUNIT5_MOCKITO, SKILL_REGRESSION_TEST}
        for skill in skills.values():
            assert skill.description and skill.when and skill.body
            assert 200 <= len(skill.body) <= 1200  # 짧게 — 필요한 것만 싣는다

    def test_frontmatter가_없으면_폴더_이름과_전체_본문이다(self):
        skill = parse_skill("- 규칙 하나\n", fallback_name="x")
        assert skill == Skill("x", "", "", "- 규칙 하나")


class TestSelection:
    def test_mock_판정이_있으면_mockito_스킬(self):
        signals = signals_from(_materials([MOCK, VALUE]), None, None)
        assert signals == SkillSignals(uses_mock=True)
        assert [s.name for s in select_skills(signals)] == [SKILL_JUNIT5_MOCKITO]

    def test_버그_수정_실행이면_재발_방지_스킬(self):
        signals = signals_from(_materials([VALUE]), {"src/main/A.java": "old"}, None)
        assert [s.name for s in select_skills(signals)] == [SKILL_REGRESSION_TEST]

    def test_둘_다면_규칙표_순서대로_둘_다(self):
        signals = signals_from(_materials([MOCK]), {"a": "b"}, None)
        assert [s.name for s in select_skills(signals)] == [
            SKILL_JUNIT5_MOCKITO,
            SKILL_REGRESSION_TEST,
        ]

    def test_신호가_없으면_스킬_없음_그리고_렌더는_빈_값(self):
        selected = select_skills(signals_from(_materials([VALUE]), None, None))
        assert selected == [] and render_skills(selected) == ""

    def test_resolve_재개_신호는_기록되지만_아직_스킬이_없다(self):
        signals = signals_from(_materials([]), None, {"calculate_emptyItems_returnsZero"})
        assert signals.resume_with_authorized is True
        assert select_skills(signals) == []


class TestRender:
    def test_이름_설명_본문이_프롬프트_형식으로_이어진다(self):
        text = render_skills(select_skills(SkillSignals(uses_mock=True)))
        assert text.startswith("[스킬: junit5-mockito — ")
        assert "MockitoExtension" in text


class TestSkillsCannotLoosenRules:
    """스킬은 '어떻게 잘 쓰나'만 담는다 — 게이트가 막는 행동을 권하는 문구가 있으면 안 된다."""

    FORBIDDEN = ("@Disabled", "@Ignore", "assumeTrue", "assumeFalse")

    def test_스킬_본문에_스킵_유도_문구가_없다(self):
        for path in SKILLS_DIR.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            for token in self.FORBIDDEN:
                assert token not in text, f"{path.parent.name}: {token}"

    def test_스킬은_core_밖에_있다(self):
        assert "core" not in SKILLS_DIR.parts and "adapters" in SKILLS_DIR.parts
