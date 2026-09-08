"""게이트웨이 tool calling 실측 — Deep Agents 전환의 사전 확인 (ADR-0024, v4 5절 확인 목록 3번).

Deep Agents는 모델이 도구를 직접 부르는 구조라, 게이트웨이가 `tools` 파라미터를 그대로
통과시키고 응답에 `tool_calls`를 돌려줘야 한다. 이 스크립트는 도구 하나를 정의해 실호출
1회로 그것을 확인한다. 통과하지 못하면 전환을 진행하지 않는다(ADR-0024 결과 절).

사용:  uv run --python 3.12 python scripts/probe_tool_calling.py [--model gpt-5]
전제:  .env 또는 환경변수에 CTA_GATEWAY_URL·CTA_GATEWAY_API_KEY (값은 절대 출력하지 않는다)
"""

import argparse
import sys

from langchain_core.tools import tool

from cta.llm.chat_model import make_chat_model


@tool
def run_tests(selector: str) -> str:
    """지정한 테스트만 실행한다. selector는 테스트 클래스 이름이다."""
    return f"통과: {selector}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="deployment 이름 (기본: CTA_LLM_MODEL 또는 코드 기본값)")
    args = parser.parse_args()

    model, deployment = make_chat_model(model_default=args.model)
    bound = model.bind_tools([run_tests])
    print(f"모델 {deployment} — 도구 1개(run_tests)를 붙여 호출한다...")
    response = bound.invoke("run_tests 도구로 OrderServiceTest를 실행하라. 다른 말은 하지 마라.")
    calls = getattr(response, "tool_calls", None) or []
    if not calls:
        print("실패: 응답에 tool_calls가 없다 — 게이트웨이가 tool calling을 통과시키지 않는다.")
        print(f"응답 본문 앞부분: {str(response.content)[:200]!r}")
        return 1
    first = calls[0]
    print(f"성공: tool_calls 수신 — {first['name']}({first['args']})")
    usage = getattr(response, "usage_metadata", None) or {}
    print(f"토큰: {usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
