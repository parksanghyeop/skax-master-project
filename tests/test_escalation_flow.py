"""사람 확인 보관소·판단 메모·토큰 계측의 단위 테스트 (SC-003 저장→재개 장치, SC-001 토큰 표시)."""

from cta.adapters.java.maven import detect_maven_project
from cta.cli.escalations import (
    Escalation,
    discard_escalation,
    get_escalation,
    list_escalations,
    make_id,
    save_escalation,
)
from cta.cli.memos import Memo, find_similar, render_memos, save_memo
from cta.cli.render import box, format_duration, render_diff_excerpt
from cta.llm.client import ChatMessage, ChatResponse
from cta.llm.metering import MeteredClient
from cta.llm.replay import RecordingClient, ReplayClient


def _project(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return detect_maven_project(tmp_path)


def _escalation(target="PricingCalculator#calculate", kind="escalate") -> Escalation:
    return Escalation(
        id=make_id(target),
        kind=kind,
        target=target,
        category="refactor",
        confidence=0.88,
        evidence=["시그니처 동일", "for문을 스트림으로 교체"],
        analysis="동작 보존 리팩터링으로 보임",
        reason="리팩터링인데 테스트 실패",
        briefing="지침",
        tests=["PricingCalculatorTest"],
        run_summary="실패",
        failed_tests=[
            {
                "name": "calculate_emptyItems_returnsZero",
                "test_class": "PricingCalculatorTest",
                "expected": "0",
                "actual": "null",
                "message": "expected: <0> but was: <null>",
            }
        ],
        file_rel="src/main/java/PricingCalculator.java",
        change_line=45,
        diff_excerpt="-        if (items.isEmpty()) return ZERO;\n+        return items.stream()",
        base="HEAD~1",
        commit_message="refactor: 스트림",
        created_at="2026-09-02T10:00:00",
    )


class TestEscalationStore:
    def test_저장_목록_조회_폐기_왕복(self, tmp_path):
        project = _project(tmp_path)
        esc = _escalation()
        save_escalation(project, esc)
        assert [e.id for e in list_escalations(project)] == [esc.id]
        loaded = get_escalation(project, esc.id)
        assert loaded == esc  # dataclass 동등성 — JSON 왕복에 손실 없음
        assert loaded.failed_tests[0]["actual"] == "null"
        discard_escalation(project, esc.id)
        assert list_escalations(project) == []

    def test_id는_시각과_대상으로_만든다(self):
        assert make_id("A#b").endswith("-A-b")


class TestMemos:
    def test_같은_메서드_사례가_먼저_최근순으로_나온다(self, tmp_path):
        project = _project(tmp_path)
        save_memo(
            project, Memo("Calc#add", "refactor", "intended", "일부러 바꿈", "2026-09-01T00:00:00")
        )
        save_memo(project, Memo("Calc#sub", "bug_fix", "proceed", "진행", "2026-09-02T00:00:00"))
        save_memo(
            project,
            Memo("Calc#add", "refactor", "test-issue", "테스트 문제", "2026-09-03T00:00:00"),
        )
        found = find_similar(project, "Calc#add")
        assert [m.decision for m in found] == ["test-issue", "intended", "proceed"]
        assert find_similar(project, "Other#x") == []
        assert "Calc.add: refactor → test-issue" in render_memos(found)
        assert render_memos([]) == ""


class TestRenderPieces:
    def test_상자와_시간_diff_발췌(self):
        title = "사람 확인 필요 — 자동으로 고치지 않았습니다"
        drawn = box(title)
        assert drawn.count("\n") == 2 and title in drawn
        assert format_duration(161) == "2분 41초"
        lines = render_diff_excerpt("-        if (x) return 0;\n+        return y;")
        assert lines[0].startswith("바뀌기 전 : if (x) return 0;")
        assert lines[1].startswith("바뀐 후   : return y;")


class _Tokens:
    def chat(self, messages, model):
        return ChatResponse(content="ok", usage_tokens=120)


class TestTokenMetering:
    def test_호출마다_토큰을_합산한다(self):
        client = MeteredClient(_Tokens())
        client.chat([ChatMessage("user", "a")], "m")
        client.chat([ChatMessage("user", "b")], "m")
        assert (client.calls, client.total_tokens) == (2, 240)

    def test_저장된_기록을_재생해도_토큰_수가_남는다(self, tmp_path):
        cassette = tmp_path / "c.json"
        RecordingClient(_Tokens(), cassette).chat([ChatMessage("user", "a")], "m")
        replayed = ReplayClient(cassette).chat([ChatMessage("user", "a")], "m")
        assert replayed.usage_tokens == 120


class TestEscalationRendering:
    """사람 확인 상자 — 테스트가 깨졌으면 종류(escalate/ask)와 무관하게 실패 상세를 보여준다."""

    def _analysis(self, category: str, kind: str):
        from cta.core.pipeline.maintain import ChangeAnalysis
        from cta.core.pipeline.models import (
            TESTS_FAIL,
            ActionDecision,
            ChangedSymbol,
            Intent,
        )

        change = ChangedSymbol("PricingCalculator#calculate", 10, 11, False, "-a\n+b")
        return ChangeAnalysis(
            change=change,
            intent=Intent(category, "분석", 0.9, ("근거",)),
            tests=["PricingCalculatorTest"],
            tests_status=TESTS_FAIL,
            run_summary="실패\nTests run: 4, Failures: 1",
            decision=ActionDecision(kind, change.target, "지침", "사유"),
            memos="",
        )

    def test_질문_항목이라도_테스트가_깨졌으면_실패_상세와_선택지를_보여준다(self):
        from cta.cli.maintain_cmd import _render_escalation

        esc = _escalation(kind="ask")
        text = _render_escalation(1, self._analysis("unclear", "ask"), esc)
        assert "사람에게 질문" in text
        assert "4건 중 1건 실패" in text
        assert "calculate_emptyItems_returnsZero" in text and "기대 0, 실제 null" in text
        assert f"cta resolve {esc.id} --intended" in text
        assert f"cta resolve {esc.id} --test-issue" in text

    def test_리팩터링_실패는_사람_확인_상자다(self):
        from cta.cli.maintain_cmd import _render_escalation

        text = _render_escalation(1, self._analysis("refactor", "escalate"), _escalation())
        assert "사람 확인 필요 — 자동으로 고치지 않았습니다" in text
        assert "수정한 테스트   0건 (일부러 안 함)" in text
        assert "PricingCalculator.java 45행 부근" in text


class TestMemoFileNames:
    def test_같은_시각에_저장해도_메모가_덮어써지지_않는다(self, tmp_path, monkeypatch):
        # Windows 시계 해상도(~15ms) 안에서 두 번 저장되면 마이크로초 타임스탬프가 같아진다
        from datetime import datetime

        import cta.cli.memos as memos_module
        from cta.cli.memos import list_memos

        class FrozenDatetime:
            @staticmethod
            def now():
                return datetime(2026, 9, 6, 12, 0, 0)

        monkeypatch.setattr(memos_module, "datetime", FrozenDatetime)
        project = _project(tmp_path)
        save_memo(project, Memo("Calc#add", "refactor", "intended", "첫째", "2026-09-01T00:00:00"))
        save_memo(
            project, Memo("Calc#add", "refactor", "test-issue", "둘째", "2026-09-02T00:00:00")
        )
        assert [m.decision for m in list_memos(project)] == ["intended", "test-issue"]
