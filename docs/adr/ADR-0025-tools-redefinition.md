# ADR-0025: R4 재정의 — 고유 도구 6개 + 하네스 내장 도구, 사람 개입 도구 `ask_user`

- 상태: 승인 (2026-09-08). ADR-0024의 부속 결정
- 관련: CLAUDE.md R4, v4 3절, `docs/contracts.md` 도구 6종 표

## 배경

R4는 "도구는 정확히 6개"다. Deep Agents는 하네스가 도구를 자동으로 붙인다 — `task`(위임), `write_todos`(계획), `ls`·`read_file`·`glob`·
`grep`(읽기), `write_file`·`edit_file`·`delete`(쓰기). 글자 그대로 읽으면 전환이 불가능하다. R4의 취지는 "에이전트에게 주는 능력을
늘리지 않는다 — 늘리고 싶으면 기존 도구의 반환을 개선한다"이지, 하네스의 계획·위임 장치를 금지한 것이 아니다.

## 결정

1. **R4를 이렇게 읽는다**: "에이전트 **고유** 도구는 정확히 6개(`inspect_target`, `query_code_graph`, `write_test`, `run_tests`,
   `check_quality`, `report_finding`)다. 하네스가 제공하는 계획(`write_todos`)·위임(`task`)·읽기(`ls`·`read_file`·`glob`·`grep`) 도구는
   고유 도구가 아니다. 7번째 고유 도구가 필요하면 먼저 사용자에게 묻는다."
2. **내장 쓰기 도구는 쓰지 않는다.** `write_file`·`edit_file`·`delete`는 `permissions=[FilesystemPermission(operations=["write"],
   paths=["/**"], mode="deny")]`로 전 경로에서 거부되고, 모델에게 보이는 도구 목록에서도 뺀다(`core/agent/build.py`). 파일을 바꾸는 길은
   `write_test`(테스트 폴더 밖 거부) 하나다. 게이트 ③(파일 범위)이 마지막 방어선이다.
3. **`ask_user`는 도구 모양의 사람 개입 장치다.** 지금의 `UserGate.ask`(v4 2.3의 ⏸)가 노드에서 도구로 옮겨 간 것이고, 고유 도구가 아니다.
   메인 에이전트만 갖는다. 서브에이전트에는 주지 않는다 — 서브가 멈추면 어디서 기다리는지 모호해진다.
4. `core/tools/`의 함수 6개는 그대로 도구의 **본체**다. `core/agent/tools.py`는 그것을 LangChain `@tool`로 감쌀 뿐 논리를 더하지 않는다.
   길이 상한(clip)·"예외 대신 문장" 규약은 본체가 지킨다.

## 결과

- CLAUDE.md R4 문구를 이 결정에 맞춰 고친다. `docs/contracts.md` 도구 표에 "내장 도구" 절을 더한다
- `tests/test_agent_deep.py`가 고정하는 불변식: 메인·서브 어디에도 `write_file`·`edit_file`·`delete`가 도구 목록에 없다,
  `ask_user`는 메인에만 있다, 고유 도구 이름 집합은 6개다
