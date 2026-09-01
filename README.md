# Code Test Agent — Claude Code 구현 킷

Claude Code로 3단계(PoC → 테스트·고도화 → E2E) 구현을 진행하기 위한 지침 묶음.

## 구성

```
CLAUDE.md                          # 항상 로드되는 규칙 (절대 규칙 R1~R7, DoD, 보고 형식)
.claude/skills/phase1-poc/         # 1단계: M0~M3, 수직 슬라이스 + poc-findings
.claude/skills/phase2-hardening/   # 2단계: M4~M7, 파이프라인·게이트·평가 하네스
.claude/skills/phase3-e2e/         # 3단계: M8, CLI·MCP·장기기억·릴리스
.claude/commands/done-check.md     # /done-check — DoD 실검증 후 4줄 보고
.claude/commands/poc-report.md     # /poc-report — poc-findings.md 생성·갱신
.claude/commands/phase-status.md   # /phase-status — 관문 대비 진행 점검
```

## 설치

1. 이 폴더 내용을 **리포지토리 루트에 병합**한다 (기존 `docs/`, 설계 문서와 같은 리포)
2. `02_상세설계_및_개발환경구축_v4.md`를 리포에 넣는다 — CLAUDE.md가 이를 최신 설계로 참조한다
3. 기존 `code-test-agent-impl` 스킬을 쓰고 있다면: R4의 `delegate_exploration`과
   "S4 루프 직접 구현" 항목이 구설계다. CLAUDE.md의 "v4에서 바뀐 결정"이 우선한다
4. Claude Code 세션 시작 시 현재 단계를 한 줄로 알려 주면 해당 스킬이 로드된다
   (예: "지금 1단계 PoC, M1 작업 중")

## 추천 플러그인

공식 마켓플레이스는 자동 등록돼 있다. 설치: `/plugin install <이름>@claude-plugins-official`

### 1군 — 전 단계 필수 (첫날 설치)

| 플러그인 | 왜 이 프로젝트에 |
|---|---|
| **pyright-lsp** | 타입 오류를 편집 중 실시간 감지. 타입 힌트가 DoD 4번이라 없으면 `/done-check`에서 뒤늦게 잡힌다 |
| **hookify** | 자연어로 훅 생성. DoD를 "지침"이 아니라 "자동 실행"으로 만드는 핵심. 아래 규칙 3개를 첫날 등록 |
| **security-guidance** | 시크릿 유출·위험한 셸 호출 감시. 게이트웨이 토큰과 샌드박스를 다루므로 필수. 기본 활성 상태면 그대로 둔다 |
| **code-review** | 커밋 전 diff 리뷰 서브에이전트. 층 분리·R규칙 위반을 사람 리뷰 전에 걸러낸다 |
| **commit-commands** | 논리 단위 소커밋 + 문서 병행 규칙을 커밋 시점에 점검 |
| **context7** | LangGraph·Neo4j 드라이버 최신 문서 주입. LangGraph API가 자주 바뀌어 학습 데이터로 짜면 낡은 코드가 나온다 |

**hookify로 첫날 등록할 규칙** (그대로 입력하면 된다)
```
/hookify 파이썬 파일을 수정한 뒤에는 항상 ruff check와 ruff format --check를 그 파일에 실행해줘
/hookify 작업을 마치기 전에 pytest -q를 실행하고, 실패하면 완료로 보고하지 마
/hookify core/ 아래 파일에 java, maven, junit, jacoco 문자열이 들어가면 경고해줘
/hookify -Dtest 인자 없는 mvn test 실행을 막아줘
```

### 2군 — 단계별 추가

| 단계 | 플러그인 | 왜 |
|---|---|---|
| 1 PoC | **feature-dev** | 계획→구현→검증 워크플로. 카파시 1·4원칙(생각 먼저, 검증 기준 먼저)을 명령으로 강제 |
| 1 PoC | **code-simplifier** | 완성 후 과한 추상화 제거. 카파시 2원칙의 사후 점검 도구 |
| 2 고도화 | **pr-review-toolkit** | 멀티에이전트 PR 리뷰. 게이트·파이프라인처럼 안전에 직결되는 변경에 code-review보다 깊은 검토 |
| 2 고도화 | Neo4j MCP (커뮤니티 `neo4j-contrib/mcp-neo4j`) | Claude Code에서 직접 Cypher를 날려 그래프 상태 확인. 쿼리 6종 디버깅이 빨라진다 |
| 3 E2E | **mcp-server-dev** | 우리 MCP 서버 구현·검증용. Claude Code가 자기가 만든 MCP 서버를 바로 테스트 |
| 3 E2E | **claude-md-management** | CLAUDE.md가 코드와 어긋났는지 정기 점검. 릴리스 체크리스트 항목 |

### 설치하지 않을 것과 이유

- **ralph-loop** (자율 반복 실행): 카파시 원칙·DoD와 정면 충돌. 이 프로젝트는 짧은 고삐가 원칙
- **jdtls-lsp** (Java LSP): 에이전트 코드는 Python. 대상 Java 프로젝트는 샌드박스 안에서만 만진다
- **Superpowers 류 대형 워크플로 프레임워크**: 자체 규칙이 CLAUDE.md와 충돌. 우리 규칙이 이미 충분히 구체적
- **frontend-design, playwright**: UI 없음

⚠️ 플러그인은 사용자 권한으로 코드를 실행하는 신뢰 컴포넌트다. 커뮤니티 것은
저장소·권한·외부 연결을 확인하고 설치한다 — 사내망 정책도 확인할 것.

## 사용 흐름 예

```
1단계 시작:  "1단계 PoC 시작. M0부터."          → phase1-poc 스킬 적용
작업 마감:   /done-check                        → DoD 실검증 보고
주간 정리:   /poc-report                        → 발견 사항 축적
단계 전환:   /phase-status                      → 관문 통과 확인 후 사용자 승인으로 전환
```
