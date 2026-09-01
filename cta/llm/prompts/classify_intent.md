아래 코드 변경의 의도를 분류하라.

[변경 요약과 단서]
$change_summary

다음 JSON 형식으로만 답하라. 설명 문장을 붙이지 않는다.
{
  "category": "<bug_fix | refactor | new_feature | unclear 중 하나>",
  "analysis": "<무엇이 어떻게 바뀌었고, 어떤 상황을 시험해야 하는지 2~4문장>"
}

분류 기준:
- bug_fix: 잘못된 동작을 고쳤다 (조건 수정, 경계값 처리, 예외 처리 추가 등)
- refactor: 동작은 그대로 두고 코드만 정리했다 (이름 변경, 구조 정리, 중복 제거)
- new_feature: 없던 동작을 새로 추가했다
- unclear: 위 셋 중 하나로 확신할 수 없다 — 확신이 없으면 반드시 unclear를 골라라.
  추측으로 bug_fix나 refactor를 고르면 안 된다.
