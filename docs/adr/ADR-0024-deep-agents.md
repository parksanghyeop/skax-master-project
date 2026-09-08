# ADR-0024: 테스트 작성 루프를 LangChain Deep Agents(메인 + 서브에이전트)로 바꾼다

- 상태: 승인 (2026-09-08). 사용자 결정 "진행시켜" — 제안 문서 `docs/딥에이전트전환안.md` §8의 5개 항목을 추천안대로 확정
- 관련: ADR-0012(LangGraph 서브그래프 — 이 결정으로 **대체**), ADR-0016(대화 압축 안 함 — **폐기**),
  ADR-0017(스킬 — 규칙표 선택 **유지**), ADR-0023(비용 — 토큰 증가를 감수, 전/후 측정), ADR-0025(R4 재정의)
- 설계 원문: `docs/딥에이전트전환안.md` (가능성 판정·역할표·그림·이행 계획)

## 배경

지금의 작성 루프(`core/writer_graph.py`)는 노드 6개짜리 LangGraph이고 매 시도가 단발 프롬프트다. 모델은 도구를 직접 부르지
못하고, 정보 수집·실행은 노드가 대신 한다. 그래서 "왜 실패했는지 더 조사해 보라"가 불가능하고, 탐색 결과와 실행 로그가 한
프롬프트에 전부 들어간다. Deep Agents는 도구 호출형 멀티턴 + 서브에이전트(컨텍스트 격리) + 요약 + interrupt를 하네스로 제공한다.

## 결정

1. **범위는 테스트 작성 루프와 그 조립부뿐이다.** 변경 추출·의도 분류(단발 호출)·규칙표·품질 게이트·제안 보관소·escalation·메모는
   에이전트 밖 하네스에 그대로 남는다. 규칙표와 게이트를 LLM 에이전트에게 맡기는 것은 R2·R3 위반이다.
2. **메인 1 + 서브 3.** 메인 `test-lead`(계획·위임·품질 확인·한계 보고·사용자 질문), 서브 `explorer`(대상 조사·그래프 조회, 읽기 전용),
   `writer`(테스트 쓰기·실행 — 쓰기와 실행이 있는 유일한 서브), `diagnoser`(실패 원인 분석, 읽기 전용). 사람에게 묻는 권한은 메인만 갖는다.
   Deep Agents가 자동으로 붙이는 `general-purpose` 서브는 같은 이름의 읽기 전용 spec으로 **덮어써서** 무력화한다.
3. **조립 위치는 `core/agent/`.** `deepagents`는 언어 중립 라이브러리라 `langgraph`와 같은 자격으로 core에서 import한다(R1).
   backend 루트·테스트 경로는 어댑터·CLI가 넘긴다.
4. **안전장치는 미들웨어(일반 코드)로 강제한다.** 반복 상한(4회마다 질문, 8회 하드 캡), 같은 실패 반복 감지, 환경 문제 표식은
   `core/agent/limits.py`의 도구 호출 미들웨어가 `run_tests` 호출 수를 세어 판정한다 — 프롬프트 문장이 아니다.
   내장 쓰기 도구(`write_file`·`edit_file`·`delete`)는 `permissions`로 전 경로 deny. 테스트 쓰기는 `write_test` 하나뿐이다.
5. **LLM 경로.** `llm/chat_model.py`가 LangChain `AzureChatOpenAI`를 만든다(같은 환경변수, 같은 URL 규칙 — ADR-0011).
   record & replay는 모델 호출 미들웨어(`llm/model_cassette.py`)로 다시 쓴다. **기록 형식 v2**: 요청 = deployment + 정규화한 메시지
   (역할·내용·tool_calls, 메시지 id 제외), 응답 = AIMessage 직렬화 + usage. 대조는 v1과 같이 **완전 일치**다(완화하지 않는다 —
   `deepagents` 버전을 고정하면 내장 프롬프트가 안 바뀐다). 재생 모드의 모델 객체는 호출하면 예외를 던지는 `NoCallChatModel`이다 —
   실호출 폴백은 구조적으로 불가능하다(R7).
6. **의도 분류는 옛 클라이언트(`llm/gateway.py` + 카세트 v1)에 남긴다.** 단발 호출이라 도구 호출이 필요 없고, `cta eval --intents`의
   측정 자산(ADR-0020)과 기존 기록을 유지하기 위해서다. 한 층에 두 클라이언트가 있는 것은 4단계(측정 뒤 정리)에서 다시 본다.
7. **단계 도입.** `--engine deep`(기본은 `legacy`)으로 두 경로가 공존한다. 4단계에서 SC-001~003 전/후 수치를 본 뒤 기본값을 바꾸고
   `writer_graph.py`·`generation.py`를 삭제한다. 수치 없이 삭제하지 않는다(phase2 규칙).
8. **ADR-0016을 폐기한다.** 도구 호출형 멀티턴이 되었으므로 그 ADR이 적어 둔 폐기 조건에 해당한다. 압축은 Deep Agents 내장 요약
   미들웨어가 맡고, 별도 압축 규칙은 쓰지 않는다.

## 새 의존성 (승인됨)

`deepagents`(0.7.x 고정), `langchain`(1.x), `langchain-openai`(1.x). `langgraph`는 1.2로 상향된다.
Python 3.11 이상이 필요하다 — 이 PC의 기본 `python`은 3.10이라 `uv run --python 3.12`로 실행한다(`docs/개발환경.md`).

## 결과·검증

- 1단계: `tests/test_model_cassette.py`(녹음→재생 왕복, 불일치·없음 → `CassetteError`, 예산), `tests/test_chat_model.py`
- 2단계: `tests/test_agent_deep.py` — 대본 모델 + Fake 포트로 메인→explorer→writer→품질 확인 흐름, 상한 미들웨어, 쓰기 도구 deny
- 게이트웨이 tool calling 실측은 `scripts/probe_tool_calling.py` — 이 PC에는 게이트웨이가 없어 **미실행**. 막히면 전환을 중단한다
- 4단계(전/후 측정)는 측정 환경에서 한다. 그 전까지 기본 엔진은 `legacy`
