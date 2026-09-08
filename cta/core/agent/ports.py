"""Deep Agent가 쓰는 포트 묶음 — 실물(어댑터·LLM)과 Fake를 통째로 갈아끼운다 (ADR-0024).

층: core — 포트와 모델 객체의 타입만 안다. 모델은 llm 층(`make_chat_model`)이 만들어 넘기고,
녹음·재생·토큰 합산 미들웨어도 llm 층이 만든 인스턴스를 그대로 받는다(R7).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from cta.core.ports import (
    CodeGraph,
    QualityChecker,
    SourceInspector,
    TestRunner,
    TestWriter,
    UserGate,
)


@dataclass
class AgentPorts:
    """메인·서브에이전트 조립 재료.

    project_root: 내장 읽기 도구(read_file·glob·grep)의 루트. 쓰기는 전 경로 deny(ADR-0025).
    language / framework / style_notes: writer 프롬프트의 빈칸 — 언어 이름은 호출부(cli)가
      채운다(R1).
    llm_middleware: 녹음 또는 재생 + 토큰 합산. 메인·서브 전부에 같은 인스턴스가 들어간다.
    progress: 진행 보고 콜백(기본 무음). 문구는 언어 중립이다(R1).
    """

    inspector: SourceInspector
    graph: CodeGraph
    writer: TestWriter
    runner: TestRunner
    checker: QualityChecker
    gate: UserGate
    model: BaseChatModel
    project_root: Path
    language: str = ""
    framework: str = ""
    style_notes: str = ""
    llm_middleware: list = field(default_factory=list)
    progress: Callable[[str], None] = field(default=lambda _msg: None)
