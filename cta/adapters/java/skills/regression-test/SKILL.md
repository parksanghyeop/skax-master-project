---
name: regression-test
description: 버그 수정 커밋의 재발 방지 테스트 — 수정 전 코드에서는 실패하고 수정 후 코드에서는 통과해야 한다
when: 변경 의도가 버그 수정이고 조치가 테스트 추가일 때 (게이트 regression이 붙는 실행)
---
- 잡아야 하는 것은 "그 버그"다. 작업 지침서의 변경 내용(예: `>` → `>=`)에서 경계 입력을 그대로 뽑는다 —
  경계값 자체(같음), 바로 아래, 바로 위 세 케이스를 각각 한 테스트로.
- 수정 전 코드에서도 통과하는 테스트는 재발 방지 테스트가 아니다. 고친 조건이 결과를 바꾸는 입력만 고르고,
  assert에는 정확한 기대값을 쓴다(`assertNotNull`·`assertTrue(true)`처럼 무엇이든 통과하는 확인 금지).
- 테스트 이름에 버그 맥락을 남긴다: `applyDiscount_amountEqualsThreshold_appliesDiscount`. 이슈 번호가
  있으면 `@DisplayName("#4821 …")`으로 붙인다.
- 예외가 수정 대상이면 `assertThrows(IllegalArgumentException.class, () -> …)`로 예외 타입까지 고정한다.
- 기존 테스트 메서드와 assert는 한 글자도 바꾸지 않는다. 새 메서드만 추가한다.
