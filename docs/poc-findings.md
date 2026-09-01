# poc-findings.md — 1단계 PoC 발견 사항 축적

제출 양식(핵심 구현 / 문제 해결·리서치 / 핵심 동작 검증)의 원재료 파일.
완성 시점마다 그 자리에서 기록한다 — 리서치 출처는 나중에 복원이 안 된다.

## 구현 내역 (→ 양식 1. 핵심 구현 내용)

### 워크플로우
- (M3에서 기록 예정: LangGraph 서브그래프, 상태 정의, interrupt 골격)

### 도구·함수 연동
- **[M0] 포트·Fake 어댑터 골격** (2026-09-01)
  - 구현 기능: core 포트 2종(SourceInspector, TestRunner)과 인메모리 Fake, 도구 반환 길이 상한(clip)
  - 동작 원리: core는 Protocol 인터페이스만 정의하고 구체 구현은 adapters/에 격리.
    빈 selector는 어댑터가 EmptySelectorError로 결정적 거부(R5)
  - 주요 기술: Python Protocol(구조적 타이핑), frozen dataclass, pytest

### 데이터·컨텍스트
- (M2~M3에서 기록 예정: 파싱 기반 few-shot 검색, record & replay)

## 문제·리서치 로그 (→ 양식 2. 문제 해결 및 기술 리서치)

- **[이슈 구분: 환경/문서] v4 설계 원문이 리포에 없음 → 해결** (2026-09-01)
  - 문제와 원인: CLAUDE.md가 진실의 원천으로 지정한 v4 원문이 M0 착수 시점에 리포에 없었다
  - 적용한 해결: M0는 CLAUDE.md·스킬로 역산 진행 → 사용자가 `docs/`에 원문 반입 →
    contracts.md·architecture.md를 v4 기준으로 대조·동기화. 충돌 없음 확인
  - 남은 일: v4 부록이 참조하는 상세 문서(ADR 9건, `docs/design/diagrams.md`,
    `references/build-order.md`)는 여전히 미반입. 새 ADR 번호는 10번부터 쓰면 안전하나
    기존 결정 원문이 없으므로, 기존 ADR과 충돌 의심 시 사용자에게 확인한다

## 검증 캡처 (→ 양식 3. 핵심 동작 검증)

- (M3 골든 케이스에서 기록 예정. 카세트는 evals/golden/에 커밋)

## 설계 수정 필요 — v4 문서·ADR과 다르게 가야 하는 지점 + 이유 (→ ADR 후보)

- `TOOL_OUTPUT_MAX_CHARS = 4000`은 임시값 — v4 원문에 상한이 정의돼 있는지 확인 필요

## 2단계 반영 목록 — 우선순위 순

- (아직 없음)

## 측정 메모 — 토큰/시간/재시도 횟수 대략값

- (M2 이후 기록)

## 1주차 확인 의무 3건 (설계 미확정 — 사내 환경 확인 필요)

| # | 확인할 것 | 상태 |
|---|---|---|
| 1 | 게이트웨이 임베딩 API 제공 여부 | ⏳ 미확인 — 사내망 접근 필요 |
| 2 | Neo4j 별도 구동 가능 여부(사내망) | ⏳ 미확인 |
| 3 | 모델별(Kimi/Qwen/GLM) tool calling 지원 여부 | ⏳ 미확인 — 미지원 시 JSON 파싱 폴백 확정 |
