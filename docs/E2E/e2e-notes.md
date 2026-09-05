# e2e-notes.md — 3단계(E2E 서비스) 작업 기록

`hardening-notes.md`(2단계)와 같은 형식. 작업목록.md의 항목 번호를 단다.

## 구현 내역

### 1주차 M8-a 마감 — A-1·A-2·A-3·A-4·A-5·A-6 (2026-09-06)

- **결함 수정(착수 전 발견)**: `cli/memos.py` `save_memo`가 파일명을 마이크로초 타임스탬프로만 만들어
  Windows(시계 해상도 ~15ms)에서 연속 저장 시 덮어써짐 → 메모 1건 소실. 같은 자리 수 순번(`-00`, `-01`)을
  붙여 해결. 발견 경위: 3.12 환경에서 `pytest -q` 1건 실패(`TestMemos`). 회귀 테스트 `TestMemoFileNames`
- **A-1 CI**: `.github/workflows/ci.yml` — `check`(py 3.11/3.12: ruff check·format, `pytest -q` 재생 모드,
  게이트웨이 키 없음) + `integration`(수동: `-m docker`, `-m neo4j` with Neo4j 서비스 컨테이너)
- **A-2 설정 파일**: `core/config.py` `load_config` → `CtaConfig(gates, retry, gateway_timeout_sec, model,
  max_tokens_per_run)`. `cta.toml` 절 5개([gates][retry][gateway][llm][budget]). 우선순위 환경변수 > .env >
  cta.toml > 코드 기본값 — cta.toml 값은 `make_llm_client(model_default, timeout_default)` 인자로만
  들어간다(환경변수 미기록, 4주차 검토에서 setdefault를 제거). 반복 상한은 `build_writer_graph(ask_every, max_total)` 인자. 토큰 예산은 `MeteredClient(max_tokens)`가
  호출 전 검사 → `BudgetExceededError`. `gates.py`의 toml 해석은 `gate_config_from_toml`로 분리해 공유
- **A-3 시크릿**: `sandbox/docker_sandbox.py` 인자 조립을 `build_run_args`(순수 함수)로 분리 — `-e`류 옵션이
  없음을 테스트로 고정(②). `llm/masking.py` `mask_secrets` — 환경변수의 키 값 + 키 모양(`atl-…`)을 `****`로,
  CLI 출력 직전(`cli/hints.render_error`)에 적용(③). 기록 파일에 키 없음 테스트. ①은 기존 테스트
- **A-4 종료 코드·CI 사용**: `--quiet`(generate/maintain/resolve) — 경과 시간 진행 줄 생략. 사용가이드에
  종료 코드 해석과 GitHub Actions 예시 절 추가
- **A-5 에러 안내**: `cli/hints.py` — 예외·문구 → "왜 / 할 일 / 명령" 표 9행(게이트웨이 설정·시간 초과·기타,
  기록 없음, 예산 초과, pom.xml 없음, Docker 미실행, 사용자 중단, 설정 오류). `cli/main.py` 진입점이 예외를
  받아 출력 + 종료 코드 1, `CTA_DEBUG=1`이면 전체 추적
- **A-6 대화 압축**: 구현하지 않음 — ADR-0016. 근거 테스트 `TestPromptDoesNotAccumulate`

검증(이 PC, Python 3.12 임시 venv): 아래 "검증 기록" 참조.

### 2주차 M8-b 확장 — B-1 스킬 · B-5 메모 불변식 (2026-09-06)

- **B-1 워크플로우 스킬(ADR-0017)**: `adapters/java/skills/<이름>/SKILL.md` 2개(`junit5-mockito`, `regression-test`)
  + `select.py`(frontmatter 파서, `SkillSignals`, 규칙표 `_RULES`, 렌더링). `run_generation`이 재료 수집 직후
  신호(mock 판정 / 재발 방지 실행 / resolve 재개)로 스킬을 골라 `[2/4] 적용 스킬: …` 한 줄을 찍고,
  `PromptedGenerator.style_notes`에 기본 문장 뒤로 붙인다. core 무변경, 도구 6개 유지, 골든 재생 무영향
  (골든 케이스는 자체 STYLE_NOTES). 결과 dict에 `skills` 추가. wheel에 SKILL.md 포함 확인(package-data).
  멘토 확인 질문은 답이 없어 제품 워크플로우 해석으로 진행 — 개발 스킬 어필 해석이면 산출물 한 단락으로 대응
- **B-5 판단 메모 불변식**: `TestMemosCannotBypassRules` — 규칙표를 무시하라는 적대적 메모를 넣어도
  `analyze_changes`의 조치가 메모 없을 때와 같고(refactor+fail → escalate 유지), `decide()`에는 메모 인자가
  없음을 시그니처로 고정. 임베딩 검색은 게이트웨이 임베딩 API 확인 후(측정 환경) 결정
- **하지 않은 것**: 전/후 측정(B-1 5번), 결함 세트 확장(B-2), 경계값 실험(B-3), MCP(B-4) — 전부 Docker·게이트웨이가
  필요하거나(측정·`cta eval`) 사용자 결정(`mcp` 의존성)이 필요하다

### 3주차 M8-b 확장 — B-2 결함 세트 v2 · B-4 MCP 서버 (2026-09-06)

- **B-2 결함 세트 6건 → 12건(`local-defects-v2`)**: 추가 유형 — 하한 누락(clamp-lowerbound), 반복 경계(fib-loop-offbyone),
  컬렉션 순서 의존(median-unsorted, 새 메서드 `MathUtil.median`), 예외 누락(percent-exception-type, 새 메서드
  `MathUtil.percent`), 대소문자(palindrome-case), 앞 공백(countwords-leading-space). 모든 case.toml에 `probe`/`expected`.
  **`scripts/check_defects.py`** — 로컬 JDK로 버그 버전 컴파일 + probe 비교(동치 변이 탐지). 12/12 통과(이 PC JDK 23).
  CI check 잡에 setup-java + 실행 추가. Buggy.java는 고친 소스에 치환 1회를 적용해 생성(일관성)
- **[발견] v1 truncate-boundary는 동치 변이였다**: `length() <= max`를 `< max`로 바꿔도 길이==max에서 `substring(0, max)`가
  같은 문자열을 돌려줘 **관찰 불가**. 베이스라인 "5/6 미검출 1건"은 테스트가 못 잡은 게 아니라 잡을 수 없는 결함이었다 —
  실질 5/5. v2에서는 `substring(0, max - 1)`(한 글자 더 잘림)로 교체해 관찰 가능하게 했다. 자기 검사가 이런 케이스를 막는다
- **B-4 MCP 서버(ADR-0018)**: `cta/mcp/handlers.py`(cli 함수를 Namespace로 호출 + stdout 캡처, 반환 = 화면 + "종료 코드: N")
  + `server.py`(`MCPServer`에 도구 5개 등록, `cta-mcp` stdio). SDK `mcp>=2`는 선택 의존성 `[mcp]`. 도구 5개 = 명령 5개
  (generate/maintain/resolve/list_proposals/apply), 에이전트 내부 도구 6개(R4)와 별개. in-process `call_tool`로
  `list_proposals` 왕복 확인. Claude Code 등록·실호출은 측정 환경에서
- **하지 않은 것**: `cta eval` v2 베이스라인 실측(Docker·게이트웨이), B-3 경계값 실험(수치 필요)

### 4주차 검토 — 3단계 변경분 전체 diff 재검토 + 시각자료 (2026-09-06)

사용자 요청으로 `62a9bfc..HEAD`의 코드 diff(약 1,960줄)를 처음 보는 눈으로 다시 읽었다. 고친 것 4건, 기록만 한 것 6건.

**고친 것**

| # | 문제 | 왜 문제인가 | 조치 |
|---|---|---|---|
| 1 | `make_llm_client`가 cta.toml의 모델·시간 초과를 `os.environ.setdefault`로 **환경변수에 써넣었다** | MCP 서버처럼 오래 사는 프로세스가 프로젝트 A → B를 차례로 다루면 A의 cta.toml 값이 "환경변수"가 되어 B의 cta.toml을 이긴다. 우선순위 규칙이 두 번째 프로젝트부터 깨진다 | 인자로만 전달: `GatewayClient(timeout_default)` + `.timeout` 속성, `model = 환경변수 or model_default or 기본값`. 테스트 `test_cta_toml_값은_환경변수에_남지_않는다` 추가 |
| 2 | MCP 핸들러의 `redirect_stdout`은 프로세스 전역 — 서버가 도구 호출을 동시에 처리하면 두 호출의 화면이 섞인다 | 도구 결과가 뒤죽박죽이 되고, 최악의 경우 한 호출의 결과가 다른 호출로 간다 | `threading.Lock`으로 한 번에 하나만 실행. ADR-0018 3항 보강 |
| 3 | Docker 미설치 시 `subprocess`의 `FileNotFoundError` 원문(Windows: "[WinError 2] 지정된 파일을 찾을 수 없습니다")에 'docker'가 없어 오류 안내가 Docker 문제로 알아보지 못했다 | 설치 직후 가장 흔한 실패에서 안내가 일반 오류로 빠진다 | 샌드박스가 'docker'를 담은 FileNotFoundError로 다시 던진다. 테스트 `TestDockerMissing` |
| 4 | CI가 `pip install -e .`만 해서 MCP 서버 테스트가 `importorskip`으로 **항상 skip**됐다 | "CI 그린"이 MCP 등록·호출을 보증하지 않았다 | `pip install -e ".[mcp]"` |

**기록만 한 것(개선 후보)**

- 토큰 예산 검사는 **호출 전** 누적만 본다 — 한 번의 큰 호출이 상한을 넘을 수 있다. 응답 후 검사도 추가하려면 "이미 쓴 토큰"을 되돌릴 수 없으므로 의미가 작다. 문서에 명시
- `parse_skill`은 frontmatter 종료를 첫 `\n---`로 찾는다 — 본문에 수평선(`---`)을 쓰면 잘못 자른다. 현재 스킬 2개는 해당 없음. 스킬 작성 규칙에 "본문에 `---` 금지"를 적어 둘 것
- MCP는 동기 실행이라 generate 5~10분 동안 클라이언트가 기다린다(`MCP_TIMEOUT`). 비동기(시작/조회/결과)는 ADR-0018 후속
- `PoC구현.md` 메타 표의 "단위 172건"은 1단계 시점 스냅샷이다. 현재 224건은 E2E 산출물에 있다 — PoC 문서는 그대로 둔다
- `hints.py` 규칙표의 문구 일치(`"CTA_GATEWAY_API_KEY가 필요하다" in t`)는 gateway.py의 오류 문구와 한 쌍이다 — 문구를 바꾸면 테스트가 잡는다(`test_hints`)
- 결함 세트 `Buggy.java`는 스크래치 스크립트로 생성했다(치환 1회). 케이스를 손으로 고치면 고친 소스와 어긋날 수 있다 — `check_defects.py`가 "고친 소스와 같음"·"동치 변이"는 잡지만 "치환이 1군데인가"는 안 본다. 필요하면 diff 줄 수 검사 추가

**시각자료 6종 추가** (`docs/제출자료/diagrams/*.mmd` → `images/*.png`, 로컬 Chrome 렌더): `e2e-architecture`(3단계 신설 모듈이 층 구조 어디에 붙었나),
`skills-flow`(신호 → 규칙표 → 스킬 → 프롬프트), `mcp-path`(Claude Code → cta-mcp → 핸들러 → cli 함수), `config-precedence`(설정 4단계 우선순위와 행선지),
`ci-and-defects`(CI 두 잡 + 결함 세트 자기 검사), `e2e-status`(작업 항목별 완료/대기). 기존 `workflow-summary`에 스킬 선택 단계를 추가해 재렌더.

### 5주차 — 로컬 실행 모드 `--fast` (2026-09-06, 사용자 요청: Docker가 너무 오래 걸린다)

- **ADR-0019**: `--fast` = Docker 대신 이 PC의 Maven·JDK로 실행 + 커버리지·뮤테이션 게이트 생략. `--runner docker|local`로
  분리 제어(`--fast --runner docker` = 격리 유지 + 게이트만 생략). R6은 "사용자가 명시한 경우에만 로컬" 예외를 두는 것으로
  CLAUDE.md를 갱신. 코드가 스스로 로컬로 폴백하는 경로는 만들지 않았다
- **구현**: `sandbox/local_sandbox.py` `LocalSandbox`(같은 `run()` 시그니처 — `Sandbox` 프로토콜 신설, 어댑터 5개는 타입 힌트만
  변경), `sandbox/factory.py` `choose_runner`·`make_sandbox`·`LOCAL_MODE_WARNING`. 컨테이너 경로 → 호스트 경로 번역, `-o`·
  `-Dmaven.repo.local=` 제거(사용자 `~/.m2` 사용, 준비 단계 생략). generate/maintain/resolve/eval에 `runner_kind` 배선,
  `[3/4]`에 `실행: local`, 결과 `runner`. `hints.py`에 mvn 없음 안내
- **실기동(이 PC, Docker 없음, Maven 3.9.11 스크래치 설치 + JDK 23)**: evalbench `TextUtilTest` 로컬 실행 **통과 6초**,
  컴파일 검사 **2초**, 빈 selector 거부 유지(R5). Docker 경로는 같은 작업이 첫 실행 3~5분
- **미검증**: `cta generate --fast` 전체(게이트웨이 필요), `--runner local` 단독(커버리지·뮤테이션 게이트를 로컬 Maven으로)

## 검증 기록

- 2026-09-06 착수 전 기준선: `pytest -q` 171 passed, 1 failed(memos 덮어쓰기), 4 deselected. ruff 통과
- 2026-09-06 1주차 완료(Python 3.12 임시 venv, `PYTHONUTF8=1`): `ruff check .` 통과 · `ruff format --check .` 140 files
  · `pytest -q` **204 passed**, 4 deselected(docker·neo4j) — 신규 32건(config 6, secrets 8, hints 12, writer 한도 4,
  프롬프트 비누적 1, memos 순번 1) 포함
- CLI 스모크(이 PC, Docker·키 없음): `cta generate --help`에 `--quiet` 노출 / pom.xml 없는 폴더 → "오류 + 왜/할 일/명령"
  4줄, 종료 코드 1 / 게이트웨이 키 비운 상태 → .env 안내 4줄, 종료 코드 1. 둘 다 전체 추적(traceback) 없이 끝남
- `.github/workflows/ci.yml` — YAML 파싱 확인(jobs: check, integration). 실제 실행은 GitHub push 후
- 미검증: `--quiet`가 실제 생성 진행 줄을 끄는지(Docker·게이트웨이 필요), 토큰 예산 초과 시 되돌림 경로의 실호출 재현
- 2026-09-06 2주차(B-1·B-5): ruff 통과 · `pytest -q` **216 passed**(신규 12: skills 10, 메모 불변식 2) ·
  `uv build --wheel`로 `cta/adapters/java/skills/*/SKILL.md` 포함 확인. 스킬이 실제 프롬프트에 들어간 실호출·전/후 수치는 미측정
- 2026-09-06 3주차(B-2·B-4): ruff 통과 · `pytest -q` **222 passed**(신규 6: mcp 핸들러 5 + 서버 1) ·
  `python scripts/check_defects.py` **12/12 통과** · MCP SDK 2.x in-process 도구 5개 등록·호출 확인
- 2026-09-06 4주차(검토)·5주차(로컬 모드): ruff 통과 · `pytest -q` **232 passed**(검토 2 + 로컬 샌드박스 8) · 로컬 모드 실기동 6초/2초

## 문제·리서치 로그

- **[Windows] 마이크로초 타임스탬프 파일명 충돌** — `datetime.now()`가 같은 값을 돌려줄 수 있다(시계 해상도).
  파일명 유일성을 시각에만 의존하지 않는다. 다른 보관소(escalations `make_id`는 초 단위 + 대상 이름,
  proposals는 클래스 이름)는 이름에 의미 있는 키가 있어 해당 없음
- **[설계] 설정 우선순위** — cta.toml이 .env보다 낮은 이유: .env는 사람·기계 단위(키·주소·개인 모델 선택),
  cta.toml은 커밋되는 프로젝트 단위. 커밋된 파일이 개인 설정을 덮으면 놀랍다. 반대 의견이 있으면 ADR로

## 남은 것 (1주차 이후)

- CI: GitHub Actions `ci` check 잡 success — 50fa679(B-5), 6f63f91(B-4, check_defects 포함) (2026-09-06 API 확인). integration 잡은 수동 실행 대기
- `--quiet` 실사용 확인은 Docker·게이트웨이가 있는 환경에서(이 PC는 Docker·키 없음)
