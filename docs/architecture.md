# architecture.md — 구조와 의존 방향

> ⚠️ v4 설계 원문 부재 상태에서 M0 스캐폴딩 기준으로 작성. 원문 입수 시 대조 필요.

## 층 구조와 의존 방향

```
tests ──▶ (모든 층)
adapters ──▶ core        # 구체 구현이 포트에 의존
llm      ──▶ (독립)      # 게이트웨이 호출 전용 통로 (M2)
core     ──▶ (없음)      # 가장 안쪽. 바깥 층 import 금지
```

- **core는 언어를 모른다(R1)**: 언어·빌드 도구 이름 문자열 금지.
  `tests/test_layering.py`가 금지 문자열과 import 방향을 함께 검사한다.
- **LLM 호출은 llm/만 경유(R7)**: record & replay가 작동해야 하므로.

## 모듈 표

| 모듈 | 책임 | 등장 마일스톤 |
|---|---|---|
| `core/__init__.py` | core 층 선언·규칙 안내 | M0 |
| `core/ports.py` | 포트(SourceInspector, TestRunner)와 데이터 모델 | M0 |
| `core/textlimit.py` | 도구 반환 문자열 길이 상한(clip) | M0 |
| `adapters/fake.py` | 포트의 인메모리 Fake 구현 — 오프라인 테스트·데모용 | M0 |
| `llm/__init__.py` | llm 층 자리 표시 (클라이언트·record&replay는 M2) | M0 |
| `llm/prompts/` | 프롬프트 파일 보관소 (코드에서 분리) | M0 |

## M0에서 한 구조 결정 (v4 원문과 대조 필요)

1. **src 레이아웃 대신 최상위 패키지** `core/ adapters/ llm/` — CLAUDE.md의 층 표기와
   디렉터리가 1:1로 일치해 test_layering 검사와 독자의 머릿속 지도가 단순해진다.
2. **포트는 Protocol** — Fake·실물 어댑터가 상속 없이 구조적으로 들어맞는다.
3. **빈 selector 거부는 어댑터 책임** — R5 원문("어댑터가 빈 selector를 거부한다") 그대로.
   공통 계약이므로 어댑터 테스트가 반드시 검증한다.
