# hardening-notes.md — 2단계(테스트·고도화) 작업 기록

1단계의 poc-findings.md와 같은 용도 — 완성 시점마다 그 자리에서 기록한다.
평가 수치는 evals/results/에 버전과 함께 별도 보관(고도화 규칙: 수치 없는 개선 금지).

## 구현 내역

### M4 — 코드 그래프 (2026-09-01)
- 구현 기능: 그래프 계층(graph/) — 노드(클래스·메서드)·확정 엣지 3종(DECLARES·
  CREATES·COVERS), 인메모리+Neo4j 저장소, 질의 응답(GraphCodeGraph),
  Java 빌더, JaCoCo 실측 수집기, build_graph CLI
- 동작 원리: 정적으로 100% 확정되는 관계만 그래프에 넣는다(v4 4.1). COVERS는
  테스트 클래스 단위 JaCoCo 실측 — 추측이 아니라 실행 기록. query_code_graph
  도구가 CodeGraph 포트로 실응답(3종)·안내(후순위 3종)를 돌려주고 답은 800토큰 상한.
  그래프 미구축 환경은 ParsingCodeGraph 폴백으로 동작(재생 호환 유지)
- 검증: 실제 Neo4j 컨테이너에 examples/demo 빌드 —
  verifying_tests(add)=CalculatorTest(실측), verifying_tests(divide)=없음(정확),
  how_to_create=테스트 우선 발췌. 왕복 통합 테스트(neo4j 마커) 통과,
  단위 66 passed, 대표 시나리오 재생(docker) 2 passed 유지

## 문제·리서치 로그

- **[이슈: 설계] 스킬의 ADR-0010 번호 충돌** — phase2 스킬이 예정한 ADR-0010
  (LangGraph 루프)을 LLM 백엔드 결정이 먼저 사용 → ADR-0012로 소급 기록, 번호
  주석 명시
- **[이슈: 도구 연동] COVERS의 귀속 단위** — JaCoCo는 실행 전체의 커버리지를
  주므로 테스트 "메서드"별 귀속은 메서드별 격리 실행이 필요해 비용이 큼.
  테스트 "클래스" 단위 실측으로 시작(알려진 한계로 계약에 기록). 메서드 단위가
  필요해지면 M7 하네스에서 비용 대비 효과를 측정 후 결정
- **[이슈: 캐시] JaCoCo 플러그인이 기존 캐시에 없음** — 준비 단계 예열에 jacoco
  goals를 포함시켜 해결. 기존 캐시는 삭제 후 재준비 필요(사용가이드에 반영 예정)

## 남은 스텁·후순위

- CALLS 엣지(확신도 포함) — 후순위, callers 쿼리는 안내 문장
- implementations·touches_outside 쿼리 — 후순위
- 증분 갱신(바뀐 파일만) — M5 변경 추출과 함께
- generate_test.py의 그래프 사용 옵션(현재 파싱 폴백 고정) — M5 파이프라인 배선 시
