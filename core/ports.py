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
