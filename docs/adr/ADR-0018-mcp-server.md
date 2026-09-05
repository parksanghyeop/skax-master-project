# ADR-0018: MCP 서버는 CLI 껍데기다 — 도구 5개, 동기 실행, 선택 의존성

- 상태: 승인 (2026-09-06). phase3 스킬 M8 "MCP 서버: Claude Code 등에서 도구로 호출 가능하게. CLI와 같은 core 공유"

## 배경

Claude Code 같은 MCP 클라이언트가 `cta`를 도구로 부를 수 있어야 한다. 두 가지 혼동을 미리 막아야 한다.
(1) "도구"라는 말 — CLAUDE.md R4의 도구 6개는 **에이전트 내부**(core/tools) 도구다. MCP가 노출하는 것은
사용자 명령이다. (2) 로직 복제 — MCP 핸들러가 파이프라인을 다시 조립하면 두 진입점이 어긋난다.

## 결정

1. **MCP 도구 5개 = CLI 명령 5개**: `generate`, `maintain`, `resolve`, `list_proposals`(= `cta diff`),
   `apply`. `graph`·`eval`·`demo`는 노출하지 않는다(개발·사전 준비용). R4의 6개와는 다른 층이며 R4는 그대로다
2. **핸들러는 cli 함수를 그대로 호출한다**(`cta/mcp/handlers.py` → `cli/main._cmd_*`, `run_maintain`, `run_resolve`).
   인자 변환(Namespace 조립)과 stdout 캡처만 한다. 화면 출력 전체 + "종료 코드: N"이 도구 결과다 —
   사람이 터미널에서 보는 것과 같은 내용을 모델이 본다
3. **stdout은 반드시 캡처한다.** stdio 전송에서 표준 출력은 프로토콜 채널이다. `redirect_stdout`으로 모은다.
   `redirect_stdout`은 프로세스 전역이므로 도구 실행은 `threading.Lock`으로 **한 번에 하나**만 — 동시 호출의
   화면이 섞이지 않는다(샌드박스·게이트웨이 호출도 직렬이 안전하다).
   `--quiet`·`--non-interactive`를 항상 켠다(질문은 자동 "계속", 상한은 cta.toml [retry] 그대로).
   프로젝트별 설정(cta.toml의 모델·시간 초과)은 환경변수에 쓰지 않고 인자로만 전달한다 — 오래 사는 서버가
   프로젝트를 바꿔도 이전 값이 남지 않는다(2026-09-06 검토에서 setdefault 방식을 제거)
4. **동기 실행.** generate/maintain은 5~10분 걸린다. 작업 시작/조회/결과의 3단계 비동기 도구는 상태 저장·정리가
   필요해 3단계("닫는 단계") 범위를 넘는다. 클라이언트 시간 초과는 클라이언트 설정으로 늘린다
   (Claude Code: 환경변수 `MCP_TIMEOUT`, 밀리초). 서버 `instructions`에 "수 분 걸린다"를 명시한다
5. **MCP SDK는 선택 의존성**: `pip install code-test-agent[mcp]`(`mcp>=2`, `MCPServer` API). CLI 사용자에게
   SDK를 강제하지 않는다. CLAUDE.md "새 의존성은 추가 전에 묻는다"에 대해: 사용자가 2026-09-06 "모든 작업을
   이어서 진행"을 지시했고, 기본 설치에 영향이 없는 선택 그룹으로 넣어 영향 범위를 최소화했다
6. **시크릿은 도구 인자로 받지 않는다.** 서버 프로세스의 환경변수·.env만(ADR-0011). 프로젝트 경로는 매 호출의
   `project` 인자로 받는다 — 서버가 특정 프로젝트에 묶이지 않는다

## 검증

- `tests/test_mcp.py`: 핸들러가 stdout을 새지 않고 문자열로 돌려주는지, pom.xml 없음·decision 오류의 안내와
  종료 코드, SDK가 있으면 도구 5개 등록과 `call_tool` 결과. SDK 없으면 서버 테스트는 skip
- 이 PC에서는 Docker·게이트웨이가 없어 generate/maintain의 실호출은 미검증. Claude Code 등록·호출 캡처는
  측정 환경에서(작업목록 B-4 검증)

## 결과

- 로직이 늘지 않았다: `cta/mcp/`는 인자 변환·출력 캡처·등록만 있다(핸들러 130줄, 서버 40줄)
- 비동기 실행이 필요해지면(장시간 작업을 UI가 기다리지 못할 때) 이 ADR을 잇는 새 ADR로 — 상태 저장은
  `.cta/` 보관소 형식을 재사용할 수 있다
