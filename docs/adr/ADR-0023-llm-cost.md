# ADR-0023: LLM 호출 비용 — 기존 테스트 파일에는 새 메서드만 출력, 추론 강도 low, 토큰 내역 기록

- 상태: 승인 (2026-09-07). 사용자 요청 "LLM 호출 비용 최적화 — 제일 좋은 방법으로 적용"
- 관련: ADR-0012(기록·재생), ADR-0013(모델 비교), ADR-0017(스킬), 테스트및고도화 §2.2(병목 실측)

## 배경

오늘 실호출(`cta generate --class …OrderService --max-methods 2 --fast`, gpt-5) 한 번이 20,969토큰이었다.
작성 프롬프트의 출력 규칙이 "테스트 파일 **전체**"라서 기존 테스트 20개(9.6KB)를 시도마다 다시 출력했고,
재시도에는 직전 파일 전체가 다시 입력으로 들어갔다. gpt-5는 추론 토큰도 출력으로 과금되는데, 게이트웨이 응답의
`usage`에서 `total_tokens`만 기록해 입력·출력·추론·캐시를 나눠 볼 수 없었다. 공개 단가 기준으로 비용의 80% 이상이
출력 쪽이다.

## 결정

1. **토큰 내역을 기록한다.** `ChatResponse`에 `prompt_tokens`·`completion_tokens`·`reasoning_tokens`·`cached_tokens`를
   두고 게이트웨이 `usage`(`prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens`)를 읽는다.
   `MeteredClient`가 합산하고 화면 "소요 … 토큰" 뒤에 내역을, 결과 dict에 `tokens_breakdown`을 붙인다.
   수치 없는 개선 금지 규칙의 전제다. 재생 기록에는 내역이 없으므로 0으로 읽는다(호환)
2. **기존 테스트 파일에 추가할 때는 새 멤버만 출력한다.** 대상 테스트 클래스가 이미 있으면 작성 프롬프트를
   `write_test_append.md`로 바꾼다 — 출력은 "새로 필요한 import + 새 테스트 메서드(필요하면 헬퍼·필드)"만.
   `adapters/java/merge.py`의 `merge_test_members(existing, fragment)`가 import를 중복 없이 합치고 멤버를 클래스의
   마지막 `}` 앞에 넣어 **파일 전체**를 만든다. 그 뒤(파일 쓰기·실행·게이트·제안)는 지금과 같은 전체 파일을 본다.
   재시도의 "직전 시도 코드"는 파일 전체가 아니라 **직전 조각**이다(기존 파일은 [수집된 정보]에 이미 있다).
   새 테스트 클래스를 만들 때(기존 파일 없음)는 `write_test.md`를 그대로 쓴다 — 저장된 시연 기록(골든)이 이 경로라
   재생이 깨지지 않는다
3. **추론 강도 기본값 low.** 요청 본문에 `reasoning_effort`를 넣는다. 값은 `cta.toml [llm] reasoning_effort` 또는
   환경변수 `CTA_LLM_REASONING_EFFORT`(minimal/low/medium/high, `none`이면 보내지 않음), 없으면 `low`.
   deployment 이름이 추론 모델(gpt-5·o 계열)일 때만 보낸다 — gpt-4.1 등은 이 파라미터를 거부한다.
   실측(hardening-notes 2026-09-04): 짧은 작성 gpt-5 17.4초 → low 7.8초 → minimal 1.8초. 재생 대조 키(model·messages)에는
   들어가지 않으므로 기록을 다시 만들 필요가 없다
4. **하지 않은 것**: 작성 모델을 gpt-4.1로 바꾸기(비용은 비슷, 시간만 이득 — 사용자가 고르는 `[llm] model`로 충분),
   응답 캐시(시연 외 위험), Batch API(대화형에 부적합)

## 검증

- 단위: merge(import 중복·클래스 래핑 제거·들여쓰기), 생성기 append 모드(프롬프트 선택·조각→전체 합성·재시도 조각),
  게이트웨이 usage 내역·`reasoning_effort` 조건, 설정 읽기
- 실호출 전/후(같은 대상 `OrderService` delete·total, `--max-methods 2 --fast`): 전 20,969토큰 → 후는 e2e-notes 10주차
- 의도 분류 정확도(`cta eval --intents --variant with`)와 결함 세트 v1 6건(`cta eval --fast --cases …`)이 유지되는지

## 결과

- 예상: 오늘 같은 실행에서 출력 토큰 절반 이상 감소 + 추론 토큰 감소 → 전체 60~70% 절감. 실측은 e2e-notes
- 기존 테스트를 모델이 다시 쓰지 않으므로 assert 게이트가 잡을 "기존 테스트 변경" 자체가 줄어든다
