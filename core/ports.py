"""core 계층의 포트(인터페이스)와 공용 데이터 모델.

에이전트 핵심 로직이 바깥 세계(대상 프로젝트, 샌드박스)와 만나는 경계를
인터페이스로만 표현한다. 구체 구현은 adapters/에 있다. core가 어느 층인지·왜
여기 있는지: 절대 규칙 R1 — core는 대상 언어를 모르므로, 이 파일에는
언어·빌드 도구 이름이 등장하지 않는다.

시그니처를 바꾸면 docs/contracts.md를 같은 커밋에서 갱신한다.
"""

from dataclasses import dataclass
from typing import Protocol


class EmptySelectorError(ValueError):
    """빈(또는 공백뿐인) selector로 테스트 실행을 요청하면 어댑터가 던지는 예외.

    왜 필요한가: selector가 비면 전체 테스트 실행이 되는데, 전체 실행은 금지다
    (절대 규칙 R5). 모든 TestRunner 구현은 실행 전에 이 예외로 거부해야 한다.
    왜 LLM을 안 쓰는가: 이것은 결정적 안전장치다(절대 규칙 R2) — 문자열 검사
    하나로 판정되므로 판단을 끼울 이유가 없다.
    """


@dataclass(frozen=True)
class RunResult:
    """테스트 실행 한 번의 결과.

    passed: 실행한 테스트가 전부 통과했는가.
    summary: 사람·모델이 읽을 요약 문자열(실패 메시지, 통계 등).
      도구 층에서 그대로 모델에게 보여 주므로 구조화하지 않고 문자열로 둔다.
    """

    passed: bool
    summary: str


class SourceInspector(Protocol):
    """대상 프로젝트의 코드 조각을 들여다보는 포트 (도구 inspect_target의 뒷단).

    입력 target: 조회할 대상의 식별자 (예: "com.acme.Calculator#add").
      식별자 문법은 어댑터가 해석한다 — core는 불투명 문자열로만 다룬다.
    출력: 대상의 소스 텍스트. 대상이 없으면 그 사실을 설명하는 문자열
      (예외가 아니다 — 도구 반환은 모델이 읽고 다음 행동을 정하는 재료다).
    """

    def inspect(self, target: str) -> str: ...


class TestRunner(Protocol):
    """선택한 테스트만 샌드박스에서 실행하는 포트 (도구 run_tests의 뒷단).

    입력 selector: 실행할 테스트 지정자 (예: 클래스 이름). 어댑터가 해석한다.
    출력: RunResult.
    실패 시 동작: selector가 비면 EmptySelectorError (절대 규칙 R5).
      테스트 실패는 예외가 아니라 passed=False인 결과로 돌려준다.
    """

    def run(self, selector: str) -> RunResult: ...


class TestWriter(Protocol):
    """테스트 파일을 만들거나 고치는 포트 (도구 write_test의 뒷단).

    입력: path 테스트 파일 경로, code 파일 전체 내용.
    출력: 컴파일·정적 검사 결과 문자열 (모델이 읽는다).
    실패 시 동작: 테스트 폴더 밖 경로는 쓰지 않고 거부 문자열을 돌려준다
      (v4 1절 제약 ④ — 결정적 검사라 LLM 판단을 끼우지 않는다).
    """

    def write(self, path: str, code: str) -> str: ...


class SimilarTestFinder(Protocol):
    """구조가 비슷한 기존 테스트를 찾는 포트 (query_code_graph의 PoC 뒷단).

    입력: target 대상 메서드 식별자.
    출력: 모양(입력 개수·예외 유무)이 닮은 기존 테스트의 발췌 문자열 —
      프롬프트에 few-shot 예시로 첨부된다(v4 4.1 쿼리 "비슷한 모양의 테스트는?").
    없으면 "없다"는 문자열 (예외 아님).
    """

    def find(self, target: str) -> str: ...


class QualityChecker(Protocol):
    """완성된 테스트의 기계적 품질 검사 포트 (도구 check_quality의 뒷단).

    PoC 범위: assert 검사 1종(기존 파일의 assert 수 감소 탐지) 최소본.
    출력: 검사 결과 문자열. 왜 LLM이 없나: 품질 게이트는 결정적이어야 한다(R2).
    """

    def check(self, path: str) -> str: ...


@dataclass(frozen=True)
class UserReply:
    """중단 지점에서 사용자가 준 답. action: "continue" | "stop". hint: 추가 지시."""

    action: str
    hint: str = ""


class UserGate(Protocol):
    """반복 도중 사용자에게 묻는 포트 (v4 2.3의 ⏸ 멈춤 지점).

    PoC에서는 자동 "계속" 스텁으로 채우고, 실제 interrupt 연결은 2단계에서 한다.
    """

    def ask(self, question: str) -> UserReply: ...


class TestCodeGenerator(Protocol):
    """테스트 코드를 생성하는 포트 — LLM이 있는 곳은 이 뒤(llm/)뿐이다.

    왜 포트인가: core는 llm/을 import할 수 없다(의존 방향). LLM 구현은
    llm/generation.py에 있고, 테스트에서는 대본 있는 Fake로 바꾼다.
    입력: instruction 작업 지침서, context 수집된 정보, current_code 직전 시도(없으면 빈 값),
      last_failure 직전 실패 내용(없으면 빈 값).
    출력: 테스트 파일 전체 코드.
    """

    def generate(
        self, instruction: str, context: str, current_code: str, last_failure: str
    ) -> str: ...
