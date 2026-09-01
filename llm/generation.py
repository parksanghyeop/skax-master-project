"""프롬프트 파일 + LlmClient로 테스트 코드를 생성 — core TestCodeGenerator 포트 구현.

LLM이 실제로 등장하는 두 자리 중 하나(테스트 작성, v4 개요)다. 프롬프트는
코드에 넣지 않고 llm/prompts/ 파일에서 읽는다(phase1 스킬 규칙). 층: llm —
core는 이 파일을 모르고, 포트로만 받는다.
"""

import re
from pathlib import Path
from string import Template

from llm.client import ChatMessage, LlmClient

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# 응답에서 첫 코드 블록만 취한다 — 모델이 규칙을 어기고 설명을 붙여도 코드는 건진다.
_CODE_BLOCK = re.compile(r"```[\w]*\n(.*?)```", re.DOTALL)


def extract_code(response_text: str) -> str:
    """응답에서 코드 블록 내용을 뽑는다. 블록이 없으면 전체를 코드로 간주한다."""
    m = _CODE_BLOCK.search(response_text)
    return (m.group(1) if m else response_text).strip() + "\n"


class PromptedGenerator:
    """시스템·작성 프롬프트를 렌더링해 chat 한 번으로 테스트 코드를 얻는다.

    입력: client(실호출/녹음/재생 무엇이든), model, language·framework —
      시스템 프롬프트의 빈칸(v4 1절: 언어 자리는 실행 시점에 채운다),
      style_notes — 프로젝트 관례 설명.
    왜 Template($치환)인가: 코드 예시가 섞이는 프롬프트에서 str.format의
      중괄호 충돌을 피하기 위해서다.
    """

    def __init__(
        self,
        client: LlmClient,
        model: str,
        language: str,
        framework: str,
        style_notes: str = "",
    ) -> None:
        self._client = client
        self._model = model
        self._system = Template((_PROMPTS_DIR / "system.md").read_text(encoding="utf-8"))
        self._user = Template((_PROMPTS_DIR / "write_test.md").read_text(encoding="utf-8"))
        self._language = language
        self._framework = framework
        self._style_notes = style_notes

    def generate(self, instruction: str, context: str, current_code: str, last_failure: str) -> str:
        messages = [
            ChatMessage(
                role="system",
                content=self._system.substitute(language=self._language, framework=self._framework),
            ),
            ChatMessage(
                role="user",
                content=self._user.substitute(
                    instruction=instruction,
                    context=context,
                    style=self._style_notes,
                    current_code=current_code or "(없음)",
                    last_failure=last_failure or "(없음)",
                ),
            ),
        ]
        return extract_code(self._client.chat(messages, self._model).content)
