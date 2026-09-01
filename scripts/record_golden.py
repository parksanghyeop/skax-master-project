"""골든 카세트 녹음 스크립트 — evals/golden/generate_divide_test.json을 만든다.

두 모드:
  기본(대본):  .venv/Scripts/python scripts/record_golden.py
      ScriptedLlm의 정해진 답을 녹음한다. LLM·Docker 불필요, 결정적.
  실호출:      .venv/Scripts/python scripts/record_golden.py --live
      llm/config가 고른 백엔드(예: Claude API — .env에 키 필요)로 서브그래프
      전체를 Docker 샌드박스와 함께 실행하며 모든 LLM 호출을 녹음한다.
      재시도가 있으면 그 호출들도 카세트에 남아 재생이 그대로 재현된다.

프롬프트 재료는 golden_case가 그래프와 동일하게 만든다 — 재생 대조가 어긋나지
않기 위한 조건. 녹음 후 pytest -m docker로 재생을 검증하라.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from cta.adapters.java.inspector import JavaSourceInspector  # noqa: E402
from cta.adapters.java.maven import detect_maven_project  # noqa: E402
from cta.adapters.java.similar import JavaSimilarTestFinder, ParsingCodeGraph  # noqa: E402
from cta.core.writer_graph import build_writer_graph, gather_context  # noqa: E402
from cta.evals import golden_case as gc  # noqa: E402
from cta.llm.generation import PromptedGenerator  # noqa: E402
from cta.llm.replay import RecordingClient  # noqa: E402


def record_scripted() -> None:
    """대본 답을 1회 녹음한다 (그래프·Docker 없이 프롬프트만 동일하게 재현)."""
    project = detect_maven_project(gc.DEMO_PROJECT)
    context = gather_context(
        JavaSourceInspector(project), ParsingCodeGraph(JavaSimilarTestFinder(project)), gc.TARGET
    )
    recorder = RecordingClient(gc.ScriptedLlm([gc.SCRIPTED_ANSWER]), gc.CASSETTE)
    generator = PromptedGenerator(
        recorder, gc.SCRIPTED_MODEL, gc.LANGUAGE, gc.FRAMEWORK, gc.STYLE_NOTES
    )
    code = generator.generate(gc.INSTRUCTION, context, "", "")
    print(f"[대본 녹음] 카세트: {gc.CASSETTE}")
    print(f"생성 코드 {len(code)}자 — 첫 줄: {code.splitlines()[0]}")


def record_live() -> None:
    """설정된 백엔드로 서브그래프 전체를 실행하며 녹음한다 (Docker 필요)."""
    from cta.llm.config import make_llm_client

    client, model = make_llm_client()
    print(f"[실호출 녹음] 백엔드: {type(client).__name__}, 모델: {model}")
    recorder = RecordingClient(client, gc.CASSETTE)
    ports = gc.make_ports(recorder, model=model)
    try:
        final = build_writer_graph(ports).invoke(gc.initial_state())
    finally:
        # 생성 테스트 파일 정리 — 골든 케이스는 반복 실행 가능해야 한다
        gc.TEST_PATH.unlink(missing_ok=True)
    print(f"최종 상태: {final['status']}, 시도 {final['attempts']}회")
    print(f"실행 결과: {final['last_run'].splitlines()[0] if final['last_run'] else '(없음)'}")
    if final["status"] != "passed":
        print("⚠️ 통과하지 못했다 — 카세트를 커밋하기 전에 원인을 확인하라")
        print(final.get("report", ""))
    else:
        print(f"카세트 기록 완료: {gc.CASSETTE} — pytest -m docker로 재생을 검증하라")


if __name__ == "__main__":
    if "--live" in sys.argv:
        record_live()
    else:
        record_scripted()
