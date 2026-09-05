# ADR-0017: 테스트 작성 워크플로우에 스킬(상황별 지식 묶음)을 붙인다 — 규칙 기반 선택, 도구 추가 없음

- 상태: 승인 (2026-09-06). 사람 멘토 피드백("워크플로우에 스킬을 붙여 보라 — 기술 어필이 부족하다")의 반영.
  설계 스케치는 `docs/피드백반영계획.md` §2

## 배경

작성 프롬프트(`llm/prompts/write_test.md`)의 [프로젝트 관례] 빈칸에는 고정 문장 한 줄만 들어갔다.
Mockito 관례·재발 방지 테스트 작성법 같은 상황별 지식은 모델의 사전 지식에 맡겨져 있었고, 실측에서
1차 실패(SC-002 Mockito 오류 1건, SC-001 `--max-methods 4` 1차 실패)가 나왔다. 지식을 프롬프트 한 덩이에
전부 넣으면 토큰이 늘고 상황에 안 맞는 지시가 섞인다.

## 결정

1. **스킬 = `cta/adapters/java/skills/<이름>/SKILL.md`.** frontmatter(name·description·when) + 본문 300~1200자.
   Java 지식이므로 어댑터 아래에 둔다(R1). 새 프레임워크·언어 지원은 스킬 폴더(와 어댑터)를 더하는 일이다
2. **선택은 규칙표다**(`skills/select.py` `_RULES`: 스킬 이름 → 신호 조건). 신호(`SkillSignals`)는 이미 결정돼
   있는 값에서만 나온다 — 재료 수집의 mock 판정(`uses_mock`), 재발 방지 게이트가 붙는 실행(`regression`),
   resolve 재개(`resume_with_authorized`). LLM 판단 없음(R2). 같은 입력 → 같은 프롬프트 → 재생 가능
3. **도구를 늘리지 않는다**(R4). 스킬 로딩은 도구 호출이 아니라 `run_generation`이 프롬프트를 조립하는 시점에
   끝난다. 모델이 스킬을 탐색·선택하는 방식은 토큰·재시도·재생 대조 모두에서 손해라 채택하지 않는다
4. **주입 위치**는 `PromptedGenerator`의 `style_notes` = 기본 문장(`BASE_STYLE_NOTE`) + 선택된 스킬 렌더링.
   core는 바뀌지 않는다 — `SkillProvider` 포트도 두지 않는다(선택이 cli/adapters 안에서 끝나므로 불필요)
5. **스킬은 "어떻게 잘 쓰나"만 담는다.** 게이트·규칙표가 정한 "무엇을 해도 되나"(스킵 금지, assert 보존,
   기대값 자동 수정 금지)를 완화하는 문구는 넣을 수 없다 — `tests/test_skills.py`가 금지 토큰을 검사한다
6. **첫 스킬 2개**: `junit5-mockito`(mock 판정 시), `regression-test`(버그 수정 → 테스트 추가 시).
   후보(`boundary-values`, `spring-slice-test`, `refactor-preserve`)는 전/후 수치를 본 뒤 추가한다
7. 어떤 신호로 어떤 스킬이 붙었는지 화면 `[2/4]`에 `적용 스킬: …` 한 줄로 남기고 `run_generation` 결과에
   `skills`로 돌려준다 — 산출물의 "스킬 선택 로그"

## 검증 계획 — 수치 없는 개선 금지(phase2 규칙)

- 대상: SC-001(`--max-methods 4`), SC-002, 로컬 결함 세트(`cta eval`). 스킬 없음/있음 각 3회
- 지표: 1차 통과율, 시도 수, 토큰, 게이트 탈락 수, 검출률. 결과는 `evals/results/`에 프롬프트 해시와 함께
- 스킬 끄기 스위치: 비교 실험용으로 `cta.toml [skills] enabled = false`를 둘지는 첫 측정 때 결정한다
  (지금은 규칙표가 곧 스위치다)
- 골든 재생(`cta demo`, `evals/golden_case.py`)은 자체 `STYLE_NOTES`로 생성기를 만들므로 이 결정에 영향받지 않는다.
  실호출 시나리오의 기록 재생성은 측정 환경(Docker·게이트웨이)에서 `scripts/record_golden.py --live`

## 결과

- 이 PC(Docker·게이트웨이 없음)에서는 선택기·렌더링·불변식만 단위 테스트로 확인했다. 전/후 수치는 측정 환경에서
- 어필 문장: "에이전트의 지식을 프롬프트 한 덩이가 아니라 선택 가능한 스킬 단위로 모듈화했다. 선택은 규칙 기반이라
  재현되고, 새 프레임워크 지원은 스킬 폴더 추가로 끝난다. 도입 전/후를 같은 시나리오로 측정해 비교했다"
