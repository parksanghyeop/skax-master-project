"""도구 6개(core/tools)의 단위 테스트 — 문자열 반환·길이 상한·안내 메시지 규약."""

from adapters.fake import FakeSimilarTestFinder, FakeTestRunner
from core.tools import query_code_graph, report_finding, run_tests
from core.tools.query_code_graph import QUERY_SIMILAR_TESTS


class TestQueryCodeGraph:
    def test_similar_tests_쿼리는_실응답한다(self):
        finder = FakeSimilarTestFinder("본보기 코드")
        assert query_code_graph(finder, QUERY_SIMILAR_TESTS, "A#b") == "본보기 코드"

    def test_다른_정의된_쿼리는_그래프_없음을_안내한다(self):
        answer = query_code_graph(FakeSimilarTestFinder(), "callers", "A#b")
        assert "그래프 없음" in answer
        assert "inspect_target" in answer  # 다음 행동을 안내한다

    def test_모르는_쿼리는_허용_목록을_알려준다(self):
        answer = query_code_graph(FakeSimilarTestFinder(), "raw_cypher", "A#b")
        assert "모르는 쿼리" in answer
        assert QUERY_SIMILAR_TESTS in answer


class TestRunTests:
    def test_빈_selector는_예외가_아니라_거부_문장이다(self):
        # 어댑터는 예외를 던지지만(R5), 도구는 모델이 읽을 문장으로 바꾼다
        answer = run_tests(FakeTestRunner(), "")
        assert answer.startswith("실행 거부")

    def test_통과와_실패가_선두_단어로_구분된다(self):
        from core.ports import RunResult

        runner = FakeTestRunner({"T": RunResult(passed=True, summary="Tests run: 1")})
        assert run_tests(runner, "T").startswith("통과")
        assert run_tests(runner, "Unknown").startswith("실패")

    def test_seed는_받되_미반영을_안내한다(self):
        from core.ports import RunResult

        runner = FakeTestRunner({"T": RunResult(passed=True, summary="ok")})
        assert "seed 42" in run_tests(runner, "T", seed=42)


def test_report_finding은_보고_형식_문자열이다():
    assert report_finding("객체 생성 방법을 알 수 없다").startswith("한계 보고:")
