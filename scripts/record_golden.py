"""골든 카세트 녹음 스크립트 — evals/golden/generate_divide_test.json을 만든다.

실행: .venv/Scripts/python scripts/record_golden.py  (리포 루트에서)
게이트웨이 미접속 환경에서는 대본(ScriptedLlm)을 녹음하고, 사내망에서는
GatewayClient로 바꿔 실모델 응답을 재녹음한다. 프롬프트 재료는 golden_case가
그래프와 동일하게 만든다 — 재생 시 요청 대조가 어긋나지 않기 위한 조건.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from adapters.java.inspector import JavaSourceInspector  # noqa: E402
from adapters.java.maven import detect_maven_project  # noqa: E402
from adapters.java.similar import JavaSimilarTestFinder  # noqa: E402
from core.writer_graph import gather_context  # noqa: E402
from evals import golden_case as gc  # noqa: E402
from llm.generation import PromptedGenerator  # noqa: E402
from llm.replay import RecordingClient  # noqa: E402


def main() -> None:
    project = detect_maven_project(gc.DEMO_PROJECT)
    context = gather_context(
        JavaSourceInspector(project), JavaSimilarTestFinder(project), gc.TARGET
    )
    recorder = RecordingClient(gc.ScriptedLlm([gc.SCRIPTED_ANSWER]), gc.CASSETTE)
    generator = PromptedGenerator(recorder, gc.MODEL, gc.LANGUAGE, gc.FRAMEWORK, gc.STYLE_NOTES)
    code = generator.generate(gc.INSTRUCTION, context, "", "")
    print(f"카세트 기록: {gc.CASSETTE}")
    print(f"생성 코드 {len(code)}자 — 첫 줄: {code.splitlines()[0]}")


if __name__ == "__main__":
    main()
