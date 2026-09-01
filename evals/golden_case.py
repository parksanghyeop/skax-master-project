"""골든 케이스 배선 — "Calculator#divide에 새 테스트 생성" 시나리오의 단일 정의.

녹음 스크립트(scripts/record_golden.py)와 재생 테스트(tests/test_golden_case_docker.py)가
이 모듈 하나를 공유한다 — 두 곳의 프롬프트 재료가 조금이라도 어긋나면 카세트
재생이 실패하므로, 정의를 한 곳에 모은다. PoC는 "새 테스트 생성" 경로 하나만
하드코딩한다(phase1 스킬 범위).
"""

from pathlib import Path

from adapters.fake import ScriptedUserGate
from adapters.java.inspector import JavaSourceInspector
from adapters.java.maven import detect_maven_project
from adapters.java.quality import AssertCountChecker
from adapters.java.runner import JavaTestRunner
from adapters.java.similar import JavaSimilarTestFinder
from adapters.java.writer import JavaTestWriter
from core.writer_graph import WriterPorts, WriterState
from llm.client import ChatMessage, ChatResponse
from llm.generation import PromptedGenerator
from sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = REPO_ROOT / "examples" / "demo"
M2_CACHE = REPO_ROOT / ".cta" / "m2repo-demo"  # M1 통합 테스트와 같은 캐시를 재사용
CASSETTE = REPO_ROOT / "evals" / "golden" / "generate_divide_test.json"

TARGET = "Calculator#divide"
SELECTOR = "CalculatorDivideTest"
TEST_PATH = (
    DEMO_PROJECT
    / "src"
    / "test"
    / "java"
    / "com"
    / "example"
    / "demo"
    / "CalculatorDivideTest.java"
)
INSTRUCTION = (
    "Calculator#divide에 대한 새 테스트를 만들라. "
    "정상 나눗셈과 0으로 나누는 예외 상황을 모두 시험하라. "
    f"테스트 클래스 이름은 {SELECTOR}, 패키지는 com.example.demo."
)
LANGUAGE = "Java"
FRAMEWORK = "JUnit 5"
STYLE_NOTES = (
    "테스트 메서드 이름은 대상_상황_기대 형식(예: add_twoPositives_returnsSum). "
    "static import로 Assertions를 쓴다."
)
# 대본 녹음 시 기본 모델(deployment) 이름. 재생 시에는 카세트에 기록된 모델을 그대로
# 쓴다(cassette_model 참조) — 모델 변경 후 재녹음해도 코드 수정이 없게 하기 위해서.
SCRIPTED_MODEL = "gpt-4.1"

# 대본 응답: 게이트웨이 미접속 환경이라 골든 카세트는 이 대본을 녹음한 것이다.
# 사내망에서 실모델로 재녹음하면 이 상수는 참고용으로만 남는다(poc-findings 기록).
SCRIPTED_ANSWER = """\
```java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CalculatorDivideTest {

    @Test
    void divide_evenlyDivisible_returnsQuotient() {
        Calculator calculator = new Calculator();
        assertEquals(3, calculator.divide(12, 4));
    }

    @Test
    void divide_byZero_throwsIllegalArgumentException() {
        Calculator calculator = new Calculator();
        assertThrows(IllegalArgumentException.class, () -> calculator.divide(1, 0));
    }
}
```
"""


def cassette_model() -> str:
    """카세트에 기록된 모델 이름을 돌려준다. 카세트가 없으면 대본 기본값.

    재생은 요청(모델 포함)을 기록과 대조하므로, 재생 측 모델은 반드시
    녹음 시점의 모델과 같아야 한다 — 그 원천은 카세트 자신이다.
    """
    if CASSETTE.is_file():
        import json

        entries = json.loads(CASSETTE.read_text(encoding="utf-8"))
        if entries:
            return entries[0]["request"]["model"]
    return SCRIPTED_MODEL


class ScriptedLlm:
    """녹음용 대본 클라이언트 (LlmClient 구현) — 요청과 무관하게 대본을 돌려준다."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        return ChatResponse(content=self._answers.pop(0))


def make_ports(llm_client, model: str | None = None) -> WriterPorts:
    """실물 어댑터 + 주어진 LLM 클라이언트로 서브그래프 포트를 조립한다.

    llm_client 자리에 RecordingClient(녹음)나 ReplayClient(재생)를 꽂는다.
    model: 녹음 시에는 사용할 모델을 명시하고, 재생 시에는 생략(카세트 기록값 사용).
    """
    project = detect_maven_project(DEMO_PROJECT)
    sandbox = DockerSandbox()
    return WriterPorts(
        inspector=JavaSourceInspector(project),
        finder=JavaSimilarTestFinder(project),
        writer=JavaTestWriter(project, sandbox, M2_CACHE),
        runner=JavaTestRunner(project, sandbox, M2_CACHE),
        checker=AssertCountChecker(project),
        gate=ScriptedUserGate(),  # PoC: interrupt 자리의 자동 "계속" 스텁
        generator=PromptedGenerator(
            llm_client, model or cassette_model(), LANGUAGE, FRAMEWORK, STYLE_NOTES
        ),
    )


def initial_state() -> WriterState:
    return {
        "instruction": INSTRUCTION,
        "target": TARGET,
        "test_path": str(TEST_PATH),
        "selector": SELECTOR,
        "context": "",
        "test_code": "",
        "write_result": "",
        "last_run": "",
        "attempts": 0,
        "quality": "",
        "report": "",
        "status": "working",
    }
