# Code Test Agent (`cta`)

Java 코드가 바뀌면 그에 맞는 JUnit 테스트를 만들고 고쳐 주는 CLI 에이전트다.
LLM은 두 곳(변경 의도 판단, 테스트 코드 작성)에만 쓰고, 안전장치(규칙표·게이트 6종)는 전부 일반 코드다.
생성물은 **제안**으로 보관되고 `cta apply`를 쳐야만 소스에 반영된다.

| 상황 | 명령 | 에이전트가 하는 일 |
|---|---|---|
| 테스트가 없는 클래스를 고쳐야 한다 | `cta generate --class <클래스>` | 테스트 없는 메서드를 골라 실제로 실행되는 테스트를 만든다 |
| 버그를 고치고 커밋했다 | `cta maintain --diff HEAD~1` | 변경 의도를 판단하고 재발 방지 테스트를 추가한다. 수정 전 코드에서 실패하는지까지 확인 |
| 리팩터링했는데 테스트가 깨졌다 | `cta maintain --diff HEAD~1` | 기대값을 고치지 않고 실패 내용과 의심 위치를 정리해 멈춘다(종료 코드 3) |
| 멈춘 항목에 답한다 | `cta resolve --intended \| --test-issue \| --proceed \| --skip` | 저장된 지점부터 이어서 실행한다 |
| 결과를 검토·반영한다 | `cta diff` → `cta apply` | 제안을 보여 주고, 명령이 있을 때만 소스에 쓴다 |

## 준비물

Python 3.11+, Docker(실행 중), 사내 LLM 게이트웨이 API 키. Java·Maven은 컨테이너 안에서 돌므로 설치하지 않는다.
대상은 Maven 단일 모듈 · JUnit 5 프로젝트다. (선택) Neo4j가 있으면 "기존 테스트 찾기"가 실측 기준이 된다.

## 5분 시작

```powershell
pip install <리포지토리 경로 또는 git+주소>       # 또는 pipx install
copy .env.example $env:USERPROFILE\.cta\.env      # CTA_GATEWAY_URL / CTA_GATEWAY_API_KEY / CTA_LLM_MODEL 채우기

cd <내 Maven 프로젝트>
cta generate --class com.example.order.OrderService --max-methods 2
cta diff                                          # 제안 검토
cta apply                                         # 반영
```

첫 실행은 의존성 준비(다운로드 + 예열)로 5분쯤 걸리고 이후 `.cta/m2repo`에 캐시된다.
실패하면 화면에 "왜 / 할 일 / 명령" 세 줄이 나온다.

## 명령 요약

| 명령 | 역할 | 종료 코드 |
|---|---|---|
| `cta generate <파일명> \| --class C [--max-methods N]` | 테스트 없는 메서드에 생성 → 제안 | 0/2/3/1 |
| `cta maintain [--diff REF] [--plan-only]` | git 변경 → 건별 판단 → 규칙표 → 생성 또는 사람 확인 | 0/2/3/1 |
| `cta resolve [id] --intended\|--test-issue\|--proceed\|--skip` | 사람 확인 항목에 답해 재개 | 0/2/3/1 |
| `cta diff [이름]` / `cta apply [이름\|--all]` / `cta discard` | 제안 확인 / 반영 / 폐기 | 0 |
| `cta graph [--coverage]` | Neo4j에 코드 그래프 빌드 (선택) | 0/1 |
| `cta demo` | 저장된 LLM 호출 기록으로 대표 시나리오 재생 (비용 0) | 0/1 |

종료 코드: 0 정상 완료 · 3 사람 확인 필요(실패가 아니다) · 2 품질 미달 · 1 오류. CI에서 쓰는 법은 사용가이드 §13.
공통 옵션 `--non-interactive`(질문 없이) · `--quiet`(진행 줄 생략) · `--fast`(커버리지·뮤테이션 게이트 생략).
프로젝트 설정은 `cta.toml`(게이트 기준치·반복 상한·시간 초과·모델·토큰 예산), 시크릿은 `.env`만.

## Claude Code에서 쓰기

```powershell
pip install "code-test-agent[mcp]"
claude mcp add cta -- cta-mcp
```
도구 5개(`generate`·`maintain`·`resolve`·`list_proposals`·`apply`)가 명령과 1:1이다. 사용가이드 §14.

## 문서 지도

| 문서 | 내용 |
|---|---|
| [docs/사용가이드.md](docs/사용가이드.md) | 설치, `.env`, 명령·옵션, `cta.toml`, CI, MCP, 문제 해결, **지원 범위와 한계** |
| [docs/제출자료/PoC구현.md](docs/제출자료/PoC구현.md) | 구현 산출물 — 한눈에 보기, 최소 계약, 실행 로그 원문, 구현 범위 3구역 |
| [docs/제출자료/핵심구현.md](docs/제출자료/핵심구현.md) | 워크플로우·의도 분류·코드 그래프·게이트의 상세 |
| [docs/제출자료/시나리오수립.md](docs/제출자료/시나리오수립.md) · [examples/demo/README.md](examples/demo/README.md) | 시나리오 SC-001~004와 재현 절차 |
| [docs/architecture.md](docs/architecture.md) · [docs/contracts.md](docs/contracts.md) · [docs/adr/](docs/adr/) | 층 구조·모듈 표 / 데이터 모델·시그니처 / 설계 결정 기록 |
| [docs/E2E/](docs/E2E/) | 3단계 계획·작업 목록·릴리스 체크리스트·작업 기록 |
| [docs/개발환경.md](docs/개발환경.md) | 개발 명령, CI, Claude Code 구현 킷(스킬·플러그인) |

## 알려진 한계

Maven 단일 모듈만(멀티모듈·Gradle 미지원). 소스 파서는 정규식 기반이라 제네릭·중첩 클래스가 많은 코드에서 빗나갈 수 있다.
화면의 확신도는 모델이 매긴 값이며 코드는 이 값으로 분기하지 않는다. 전체 목록은 사용가이드 §15.

## 개발

```bash
pip install -e . pytest ruff && ruff check . && pytest -q     # 단위 172+건, Docker·Neo4j 제외
```
규칙은 `CLAUDE.md`, 개발 환경·CI는 `docs/개발환경.md`.
