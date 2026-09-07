"""LLM 비용 절감(ADR-0023)의 단위 테스트 — 전부 Fake, 실호출·Docker 없음.

검증: ① 조각 합치기(import 중복 제외·클래스 래핑 제거·들여쓰기·기존 내용 불변)
② 생성기 추가 모드(프롬프트 선택, 조각→파일 전체, 재시도에는 직전 조각만) ③ 게이트웨이
usage 내역과 reasoning_effort 조건 ④ 설정 읽기·우선순위 ⑤ MeteredClient 합산.
"""

import os
from pathlib import Path

import pytest

from cta.adapters.java.merge import merge_test_members, split_fragment
from cta.core.config import load_config
from cta.llm.client import ChatMessage, ChatResponse
from cta.llm.config import make_llm_client
from cta.llm.gateway import build_payload, parse_usage
from cta.llm.generation import PromptedGenerator
from cta.llm.metering import MeteredClient

EXISTING = """package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalcTest {
    private final Calc calc = new Calc();

    @Test
    void add_two() {
        assertEquals(4, calc.add(2, 2));
    }
}
"""

FRAGMENT = """import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

@Test
void divide_byZero_throws() {
    assertThrows(ArithmeticException.class, () -> calc.divide(1, 0));
}
"""


class TestMerge:
    def test_새_import는_기존_import_뒤에_중복_없이_멤버는_마지막_중괄호_앞에(self):
        merged = merge_test_members(EXISTING, FRAGMENT)
        assert merged.count("import org.junit.jupiter.api.Test;") == 1
        assert "import static org.junit.jupiter.api.Assertions.assertThrows;" in merged
        assert merged.index("assertThrows;") < merged.index("class CalcTest")
        assert merged.rstrip().endswith("}")
        assert "    void divide_byZero_throws() {" in merged  # 4칸 들여쓰기
        # 기존 내용은 그대로
        assert "    void add_two() {\n        assertEquals(4, calc.add(2, 2));\n    }" in merged
        assert merged.index("add_two") < merged.index("divide_byZero_throws")

    def test_클래스로_감싼_조각은_안쪽만_취하고_package는_버린다(self):
        wrapped = (
            "package com.example;\n\nclass CalcTest {\n    @Test\n    void x() {\n"
            "        assertEquals(1, 1);\n    }\n}\n"
        )
        imports, body = split_fragment(wrapped)
        assert imports == []
        assert body.strip().startswith("@Test")
        assert "class CalcTest" not in body
        merged = merge_test_members(EXISTING, wrapped)
        assert merged.count("class CalcTest") == 1
        assert merged.count("package com.example;") == 1

    def test_이미_들여쓴_조각은_다시_들여쓰지_않는다(self):
        merged = merge_test_members(EXISTING, "    @Test\n    void y() {\n    }\n")
        assert "        @Test" not in merged
        assert "    void y() {" in merged

    def test_클래스가_아닌_기존_파일은_거부한다(self):
        with pytest.raises(ValueError):
            merge_test_members("not a class", FRAGMENT)


class _ScriptedClient:
    """답을 순서대로 돌려주고, 받은 프롬프트를 기록한다."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        self.prompts.append(messages[-1].content)
        return ChatResponse(content=self._answers.pop(0))


class TestAppendMode:
    def test_기존_파일이_있으면_조각_프롬프트를_쓰고_파일_전체를_돌려준다(self):
        client = _ScriptedClient([f"```java\n{FRAGMENT}```"])
        gen = PromptedGenerator(
            client, "m", "Java", "JUnit 5", existing_code=EXISTING, merge=merge_test_members
        )
        assert gen.append_mode
        out = gen.generate("지침", "정보", "", "")
        assert "추가할 새 테스트 메서드만" in client.prompts[0]
        assert "add_two" in out and "divide_byZero_throws" in out

    def test_재시도에는_파일_전체가_아니라_직전_조각을_보낸다(self):
        client = _ScriptedClient([f"```java\n{FRAGMENT}```", "```java\n@Test\nvoid z() {}\n```"])
        gen = PromptedGenerator(
            client, "m", "Java", "JUnit 5", existing_code=EXISTING, merge=merge_test_members
        )
        first = gen.generate("지침", "정보", "", "")
        gen.generate("지침", "정보", first, "실패 로그")
        second_prompt = client.prompts[1]
        assert "divide_byZero_throws" in second_prompt  # 직전 조각
        assert (
            "add_two" not in second_prompt.split("[직전 시도에 추가했던 코드")[1]
        )  # 전체 파일 아님

    def test_기존_파일이_없으면_전체_출력_프롬프트_그대로다(self):
        client = _ScriptedClient(["```java\nclass T {}\n```"])
        gen = PromptedGenerator(client, "m", "Java", "JUnit 5")
        assert not gen.append_mode
        assert gen.generate("지침", "정보", "", "") == "class T {}\n"
        assert "테스트 파일 전체 코드를 작성하라" in client.prompts[0]


class TestGatewayPayloadAndUsage:
    def test_reasoning_effort는_추론_모델에만_붙는다(self):
        msgs = [ChatMessage("user", "hi")]
        assert "reasoning_effort" in build_payload(msgs, "gpt-5", "low")
        assert "reasoning_effort" not in build_payload(msgs, "gpt-4.1", "low")
        assert "reasoning_effort" not in build_payload(msgs, "gpt-5", None)
        assert build_payload(msgs) == {"messages": [{"role": "user", "content": "hi"}]}

    def test_usage_내역을_읽고_없으면_0이다(self):
        u = parse_usage(
            {
                "total_tokens": 100,
                "prompt_tokens": 60,
                "completion_tokens": 40,
                "completion_tokens_details": {"reasoning_tokens": 15},
                "prompt_tokens_details": {"cached_tokens": 20},
            }
        )
        assert u == {"total": 100, "prompt": 60, "completion": 40, "reasoning": 15, "cached": 20}
        assert parse_usage(None)["total"] == 0
        assert parse_usage({"prompt_tokens": "x"})["prompt"] == 0


class TestMeteredBreakdown:
    def test_내역을_합산한다(self):
        class _C:
            def chat(self, messages, model):
                return ChatResponse(
                    "ok", 10, prompt_tokens=6, completion_tokens=4, reasoning_tokens=1
                )

        m = MeteredClient(_C())
        m.chat([], "m")
        m.chat([], "m")
        assert m.breakdown() == {
            "total": 20,
            "prompt": 12,
            "completion": 8,
            "reasoning": 2,
            "cached": 0,
        }


class TestReasoningConfig:
    def test_cta_toml에서_읽고_잘못된_값은_거부한다(self, tmp_path: Path):
        (tmp_path / "cta.toml").write_text(
            '[llm]\nreasoning_effort = "minimal"\n', encoding="utf-8"
        )
        assert load_config(tmp_path).reasoning_effort == "minimal"
        (tmp_path / "cta.toml").write_text('[llm]\nreasoning_effort = "max"\n', encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(tmp_path)

    def test_우선순위_환경변수_toml_기본값_low_그리고_none(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CTA_GATEWAY_URL", "https://example.invalid")
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", "atl-test-key")
        monkeypatch.delenv("CTA_LLM_REASONING_EFFORT", raising=False)
        no_dotenv = tmp_path / "none.env"

        client, _ = make_llm_client(no_dotenv)
        assert client._reasoning_effort == "low"
        client, _ = make_llm_client(no_dotenv, reasoning_effort_default="high")
        assert client._reasoning_effort == "high"
        client, _ = make_llm_client(no_dotenv, reasoning_effort_default="none")
        assert client._reasoning_effort is None
        monkeypatch.setenv("CTA_LLM_REASONING_EFFORT", "minimal")
        client, _ = make_llm_client(no_dotenv, reasoning_effort_default="high")
        assert client._reasoning_effort == "minimal"
        assert "CTA_LLM_REASONING_EFFORT" in os.environ  # 환경변수는 건드리지 않는다
