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
  cta.toml > 코드 기본값 — cta.toml 값은 `make_llm_client(model_default, timeout_default)`가 setdefault로만
  놓는다. 반복 상한은 `build_writer_graph(ask_every, max_total)` 인자. 토큰 예산은 `MeteredClient(max_tokens)`가
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

## 문제·리서치 로그

- **[Windows] 마이크로초 타임스탬프 파일명 충돌** — `datetime.now()`가 같은 값을 돌려줄 수 있다(시계 해상도).
  파일명 유일성을 시각에만 의존하지 않는다. 다른 보관소(escalations `make_id`는 초 단위 + 대상 이름,
  proposals는 클래스 이름)는 이름에 의미 있는 키가 있어 해당 없음
- **[설계] 설정 우선순위** — cta.toml이 .env보다 낮은 이유: .env는 사람·기계 단위(키·주소·개인 모델 선택),
  cta.toml은 커밋되는 프로젝트 단위. 커밋된 파일이 개인 설정을 덮으면 놀랍다. 반대 의견이 있으면 ADR로

## 남은 것 (1주차 이후)

- CI는 GitHub에 push해야 실제로 돈다 — 이 PC에서는 yml 문법과 로컬 동등 명령만 확인
- `--quiet` 실사용 확인은 Docker·게이트웨이가 있는 환경에서(이 PC는 Docker·키 없음)
