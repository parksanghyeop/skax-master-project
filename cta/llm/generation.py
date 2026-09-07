"""프롬프트 파일 + LlmClient로 테스트 코드를 생성 — core TestCodeGenerator 포트 구현.

LLM이 실제로 등장하는 두 자리 중 하나(테스트 작성, v4 개요)다. 프롬프트는
코드에 넣지 않고 llm/prompts/ 파일에서 읽는다(phase1 스킬 규칙). 층: llm —
core는 이 파일을 모르고, 포트로만 받는다.
"""

import re
from collections.abc import Callable
from pathlib import Path
from string import Template

from cta.llm.client import ChatMessage, LlmClient

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
        existing_code: str = "",
        merge: Callable[[str, str], str] | None = None,
    ) -> None:
        """existing_code + merge가 주어지면 **추가 모드**(ADR-0023 결정 2): 프롬프트가
        write_test_append.md로 바뀌어 모델은 새 멤버 조각만 출력하고, merge(existing, fragment)가
        파일 전체를 만든다. 둘 중 하나라도 없으면 지금까지처럼 파일 전체를 출력받는다.
        """
        self._client = client
        self._model = model
        self._system = Template((_PROMPTS_DIR / "system.md").read_text(encoding="utf-8"))
        self._append = bool(existing_code) and merge is not None
        prompt_file = "write_test_append.md" if self._append else "write_test.md"
        self._user = Template((_PROMPTS_DIR / prompt_file).read_text(encoding="utf-8"))
        self._language = language
        self._framework = framework
        self._style_notes = style_notes
        self._existing_code = existing_code
        self._merge = merge
        self._last_fragment = ""  # 추가 모드의 재시도에 "직전 시도 코드"로 보내는 조각

    @property
    def append_mode(self) -> bool:
        return self._append

    def generate(self, instruction: str, context: str, current_code: str, last_failure: str) -> str:
        # 추가 모드에서는 파일 전체 대신 직전 조각을 보낸다 — 기존 파일은 [수집된 정보]에 이미 있다
        previous = self._last_fragment if self._append else current_code
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
                    current_code=previous or "(없음)",
                    last_failure=last_failure or "(없음)",
                ),
            ),
        ]
        code = extract_code(self._client.chat(messages, self._model).content)
        if not self._append:
            return code
        self._last_fragment = code
        return self._merge(self._existing_code, code)
