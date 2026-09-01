# ADR-0011: 사내 게이트웨이(Azure OpenAI 호환) 직결 — ADR-0010 폐기

- 상태: 승인 (2026-09-01, 사용자 지시). **ADR-0010을 대체한다**
- 관련: v4 5절(기술 스택), 6.6(시크릿), 절대 규칙 R7

## 배경

ADR-0010은 사내망 미접속을 전제로 개발용 Claude 백엔드를 두는 이원화였다.
사내 게이트웨이 스펙이 확정되어(Azure OpenAI 호환 API) 개발 환경에서도 직접
접속이 가능해졌으므로, 백엔드를 하나로 줄인다.

## 결정

1. **LLM 백엔드는 사내 게이트웨이 하나다.** Claude 클라이언트·anthropic SDK
   의존성을 제거한다. 클라이언트 생성은 계속 `llm/config.py`의
   `make_llm_client()`만 경유한다(전환 지점 유지 — 스펙이 또 바뀌면 여기만 고친다).
2. **게이트웨이는 Azure OpenAI 호환 형식이다.**
   - 경로: `{base}/openai/deployments/{deployment}/chat/completions?api-version={ver}`
   - deployment 이름이 곧 모델 선택이다 — LlmClient.chat의 `model` 인자를
     deployment 이름으로 그대로 쓴다
   - 인증: `api-key` 헤더
3. **서버 주소·API 키는 리포에 기록하지 않는다**(v4 6.6). 둘 다 환경변수 또는
   `.env`(gitignore)로만. 커밋되는 `.env.example`에는 키 이름과 자리 표시만 둔다.
   API 버전 문자열은 스펙(비밀 아님)이므로 코드 상수로 두되 환경변수로 덮어쓸 수 있다.

## 결과

- 임베딩 API가 게이트웨이에 존재한다(text-embedding-3-large/small, ada-002) —
  v4 4.1 ④ 보조 검색(임베딩)이 2단계에서 가능해진다. 1주차 확인 1번 해소.
- tool calling은 Azure OpenAI chat completions가 스펙상 지원 — 모델(deployment)별
  실지원 여부는 키 확보 후 실호출로 확인한다(확인 3번).
- 골든 카세트는 deployment 이름이 대조 키에 포함되므로, 대본 카세트의 모델
  이름을 실제 deployment(`gpt-4.1`)로 맞춰 재녹음한다. 실모델 재녹음은
  `record_golden.py --live`로 키 설정 후 수행.
