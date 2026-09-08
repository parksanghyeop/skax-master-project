"""Deep Agent 조립 — 메인 test-lead + 서브 explorer/writer/diagnoser (ADR-0024).

파일 배치(1역할 1파일): ports(재료) · tools(도구 래퍼) · limits(안전장치 미들웨어) ·
subagents(서브 정의) · build(조립·실행) · prompts/(시스템 프롬프트).
층: core — deepagents·langchain은 langgraph와 같은 자격의 언어 중립 라이브러리다(R1).

이 파일에는 엔진 이름 상수만 둔다 — CLI 인자 정의가 무거운 모듈(generate)을 import하지 않고
쓰기 위해서다. 서브모듈은 여기서 import하지 않는다.
"""

# 작성 엔진(ADR-0024 결정 7). legacy = 옛 작성 그래프(단발 프롬프트),
# deep = Deep Agent(메인+서브 3). 기본값은 4단계(전/후 측정) 뒤에 바꾼다.
ENGINE_LEGACY = "legacy"
ENGINE_DEEP = "deep"
ENGINES = (ENGINE_LEGACY, ENGINE_DEEP)
