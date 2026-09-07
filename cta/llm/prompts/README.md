# llm/prompts — 프롬프트 파일 보관소

프롬프트는 코드에 f-string으로 흩뿌리지 않고 이 디렉터리의 파일로 관리한다
(phase1 스킬 규칙).

- `system.md` — 역할·절대 규칙
- `write_test.md` — 새 테스트 클래스: 파일 전체 출력
- `write_test_append.md` — 기존 테스트 클래스에 추가: 새 import·멤버 조각만 출력, 합치기는 `adapters/java/merge.py` (ADR-0023)
- `classify_intent.md` — 변경 의도 분류
