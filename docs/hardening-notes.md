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

### M5 — 파이프라인: 변경 추출·의도 분류·조치 결정 (2026-09-01)
- 구현 기능: GitChangeExtractor(diff→심볼), PromptedIntentClassifier(대분류+구체
  분석 한 호출, 실패→unclear), decide 규칙표(+지침서 조립), run_pipeline CLI
- 동작 원리: 길(조치)은 규칙표가 정하고 LLM 분석은 지침서 내용만 채운다 —
  피해 비대칭(지침서 오류=품질 저하, 길 오류=사고)이 분리 이유(v4 2.1).
  기존 테스트 상태는 그래프 실측 COVERS로 찾은 테스트를 샌드박스에서 실행해 얻는다
- 검증: 규칙표 전 행 단위 테스트(R3 escalate 행 포함), demo에 실변경 후 CLI 실행 —
  Calculator#add 추출 → gpt-5 분류 bug_fix → COVERS로 CalculatorTest 발견·실행(pass)
  → create_test 결정 + 지침서. 단위 79 passed

### M6 — 품질 게이트 5종 + interrupt 실연결 (2026-09-01)
- 구현 기능: 게이트 5종(assert 내용 비교·스킵·파일 범위 해시·JaCoCo 커버리지·
  PIT 뮤테이션), cta.toml 기준치 설정, 생성→게이트 재시도 루프(core/submit),
  실패 분류(자동/판단 필요/불가능), LangGraph interrupt 실연결(정지→답→재개),
  파이프라인 escalate/ask의 사람 해소
- 동작 원리: 게이트는 "좋은 테스트인가"를 판단하지 않고 "규칙을 어겼는가"만
  측정한다 — 측정 불가·애매는 전부 탈락(보수적). 탈락 사유는 문장으로 모델에게
  반환돼 재시도 지침서에 붙는다(최대 3회, 소진 시 사람 확인 목록).
  PIT는 원본 pom을 건드리지 않는 복제 pom(overlay)으로 돌린다
- 검증: 게이트 불변식 단위 테스트(assert 완화·삭제·파일 삭제 / @Disabled·FQN 우회 /
  허용 목록 밖 수정·생성·삭제 → 전부 탈락, 정당 시나리오 통과) + interrupt 왕복
  (정지→힌트→재개→통과 / 중지→한계 보고) + 게이트 루프(사유 재주입 확인).
  실측 불변식(docker 통합 4건, 28분 51초): **전부 통과** — assert 없는 테스트가
  커버리지 게이트는 통과하지만 뮤테이션 게이트에서 탈락함을 실측으로 확인
  (커버리지 단독으로는 빈 테스트를 못 거른다는 v4 2.4의 전제가 실증됨).
  진짜 검증이 있는 테스트(CalculatorTest)는 뮤테이션 통과

### 관문 실연 — escalate→사람 resolve→재개 (2026-09-02, 커밋 61e2f62)
- 시나리오: demo의 add를 "동작이 바뀐 리팩터링"으로 변경(+작성자 지정 의도
  refactor — 신설 --intent 옵션, LLM 분류 생략)
- 실측 흐름: 변경 추출 Calculator#add → 그래프 COVERS로 CalculatorTest 발견·
  샌드박스 실행 → **fail 감지** → 규칙표 escalate → 터미널에서 사람이 'c' 답 →
  create_test로 전환·재개. 캡처: docs/제출자료/images/escalate-demo.png
- 의미: R3(기대값 자동 수정 금지)이 실행 경로에서 증명됨 — 자동으로 덮어쓴 것이
  없고 사람 결정 이후에만 진행

### M7 — 평가 하네스: 베이스라인 확보 (2026-09-02)
- ADR-0014: Defects4J·EvoSuite 환경 제약 보류 → 로컬 결함 세트 6건으로 대체
- **베이스라인 수치** (gpt-5, 게이트 5종 full, local-defects-v1, prompt 4f3a5818756b,
  기록: evals/results/eval-local-defects-v1-gpt-5-20260902-020408.json):
  - 게이트 승인율 6/6 (전 케이스 5게이트 전부 통과, 재시도 0)
  - **검출률 5/6 = 83.3%**, 에스컬레이션 0%, 평균 생성 시도 1.0회
  - 총 19.5분(준비 포함), 케이스당 102~148초
- 미검출: truncate-boundary (경계 off-by-one) — 생성 테스트가 길이==max 경계를
  안 다룸. → 2단계 반영 목록: "경계값 명시 프롬프트" 실험 후보 (수치 비교로 검증)
- 별도 실측: demo divide 생성 1건 — accepted 182초, 커버리지 100/100,
  뮤테이션 3/3 검출 (캡처: 제출자료/images/gates-run.png)

### CLI화 — cta 명령 체계 + 제안 흐름 (2026-09-02, 사용자 피드백)
- 배경: 스크립트 모음(python scripts/...)은 "CLI 도구"라는 제품 형태와 어긋남
- 구현: `pip install -e .` → `cta` 단일 명령 (generate/run/diff/apply/discard/
  graph/eval/demo). **v4 Step 3 실현**: 생성물은 제안(.cta/proposals/)으로만
  보관, `cta diff` 검토 → `cta apply`로만 소스 반영 (기존에는 트리에 직접 썼음)
- 검증: 제안 수명주기 단위 테스트 6건, 실 CLI 세션(generate 122초 게이트 5종
  통과 → diff → apply) 및 escalate 시나리오를 cta 명령으로 재실측·재캡처.
  scripts/의 구 진입점 5개 삭제(cli/로 이동), 단위 109 passed

### 설치형 배포 검증 — 일반 pip install로 리포 밖 실행 (2026-09-02)
- 문제 3건 발견·수정: ① 프롬프트(.md)가 wheel에 미포함 → package-data 등록
  ② .env를 리포 루트에서만 탐색 → 실행 폴더 → ~/.cta/.env 순 탐색으로 변경
  ③ demo/eval이 리포 경로 의존 → 리포 밖에서는 안내 후 종료(가드)
- 실검증: 새 venv에 비-편집 `pip install <리포>` → 임의 작업 폴더에서
  `.env`(cwd)만 두고 `cta generate --fast`(gpt-5 실호출 71초, accepted) →
  `cta apply`로 자바 프로젝트 반영 확인. 가이드 설치 절을 방법 A(일반)/B(개발)로 재작성

### 사용성 — `cta generate <파일명>` 파일 모드 (2026-09-02, 사용자 피드백)
- 배경: generate가 --project·--target 등 인자를 너무 많이 요구해 사용성이 낮음
- 구현(cli/file_mode.py): 파일 이름 하나 → 현재 폴더 하위 탐색(빌드 폴더 프루닝,
  동명 파일은 번호 선택) → pom.xml 상향 탐색으로 프로젝트 자동 인식 → 메서드
  선별(private 제외, 기존 테스트가 호출 형태로 참조하는 메서드는 건너뜀 —
  없는 것만 채우는 유지보수 동작, --all로 강제) → 메서드별 생성·제안 보관
- 검증: 탐색·계획 단위 테스트 8건 + 실측 — `cta generate Calculator.java --fast`
  한 줄로 add 건너뜀·divide 생성(gpt-5, 47초, accepted). 단위 119 passed

### 사용성 — 전 명령 인자 기본값 (2026-09-02, 사용자 피드백 2차)
- 리서치: 유사 도구의 인자 관례 비교 —
  Diffblue Cover CLI(`dcover create` 인자 없이 실행: 프로젝트=현재 폴더,
  빌드 도구 자동 감지, 지정은 좁힐 때만. cover-docs.diffblue.com) vs
  Qodo Cover-Agent(경로·명령 전부 필수 인자 → 이후 리포 스캔 자동화 모드를
  추가하며 보완. github.com/qodo-ai/qodo-cover). **Diffblue 관례 채택**
- 구현(cli/locate.py): `--project` 생략 시 현재 폴더→상위→하위 순 pom.xml 탐색
  (하나면 자동, 여럿이면 번호 선택). generate/run/diff/apply/discard/graph 전부 적용.
  apply/discard는 제안 1건이면 이름도 생략 가능, diff는 1건이면 바로 diff 출력
- 검증: 자동 인식·자동 선택 단위 테스트 7건 + 실측(프로젝트 폴더 안에서
  `cta generate Calculator.java` → `cta diff` → `cta apply` 인자 없이 왕복)

### 디렉터리 정리 — 제품 코드를 cta/ 아래로 (2026-09-02, 사용자 피드백 3차)
- 배경: 루트에 층 패키지 7개 + 문서 + 예제가 섞여 구조가 안 보임
- 구현: core/adapters/llm/graph/sandbox/cli/evals → `cta/` 아래로 이동(git mv,
  이력 보존). import는 `cta.core...` 형태로 일괄 치환(59파일 218건).
  루트는 cta/ tests/ scripts/ examples/ docs/ 5개 폴더 + 설정 파일만 남음
- 따라간 것: pyproject(packages·entry point `cta.cli.main:main`·package-data),
  test_layering(core 경로 + cta.adapters 형태 import도 금지 목록에 추가),
  리포 루트 기준 경로 상수 3곳(golden_case·eval_cmd — parents 깊이 +1)
- 검증: 단위 126 passed, ruff 통과, pip install -e . 재설치 후 cta 실행 확인


### 시나리오 정합 재작성 — 명령 체계·의도 분석 출력·저장 후 재개 (2026-09-03, ADR-0015)
- 배경(사용자 요청): 에이전트가 시나리오수립.md(SC-001~004)대로 동작하는지 대조 → 원칙은
  맞지만 사용자 면이 어긋남. 특히 **의도 분석 결과가 화면에 안 보였다**(전체 변경 묶음 1회
  분류, 확신도·근거 없음). 예제(Calculator)도 재료 수집·리팩터링 실패 상황을 보여주기에 너무 단순
- 구현:
  - 명령: `cta maintain --diff`(구 run --base --execute 폐기), `cta resolve`(판단 전달 — 신설),
    `cta generate --class <FQN> --max-methods N`(클래스당 테스트 하나, 기존 파일이면 메서드 추가)
  - 의도 분류: **변경 건별** LLM 1회, JSON(category/confidence/evidence/analysis). 단서(커밋
    메시지·이슈 번호·시그니처·접근 제어자·줄 수)는 일반 코드가 수집. 주석·공백만 변경은 LLM 없이
    trivial(규칙표 행 추가). 화면: `① 대상 / 판단 (확신도) / 근거 · / 분석 / 기존 테스트 / 참고 / 할 일`
  - 사람 개입: escalate/ask는 `.cta/escalations/<id>.json`에 저장하고 종료 코드 3 → `cta resolve
    --intended|--test-issue|--proceed|--skip`이 결정 단계 이후부터 재개. 사람이 지정한 실패 테스트만
    assert 변경 허용(게이트 허용 목록), 결정은 판단 메모(.cta/memos)로 다음 maintain의 "참고"에
  - 게이트 ⑥ regression: 재발 방지 테스트를 **수정 전 코드**(git show)에 바꿔 끼워 실행 — 통과하면
    탈락(버그를 못 잡는 테스트). try/finally 복구
  - 재료 수집(materials): 확인 항목(분기·경계값·예외·null) 정규식 열거, 객체 생성법(builder/값 객체/
    저장소 mock) 판단, 기존 테스트 파일 첨부. [4/4]에 확인 항목 충족(JaCoCo 라인)·검출력(PIT)·
    기준 낮춤 여부·소요 시간·토큰(게이트웨이 usage 합산) 출력
  - assert 게이트 보고를 테스트 메서드 단위 "바뀌기 전/후 (점수)"로(SC-004), 작성 루프 상한 8회/4회마다 질문
  - 예제: Spring Boot 3.3 주문 CRUD(OrderService/Repository/Controller, PricingCalculator, Mockito
    테스트)로 교체. SC-002/003용 커밋은 `scripts/demo_scenarios.py`가 임시 폴더에 독립 저장소로 만든다
- 실측(gpt-5, Docker):
  - SC-003(`cta maintain --diff HEAD~1`, 스트림 리팩터링 커밋): 파싱 폴백으로 PricingCalculatorTest
    발견 → 실행 4건 중 1건 실패 → 판단 "리팩터링 (확신도 90%)" + 근거 3줄(커밋 메시지·시그니처 그대로·
    빈 리스트 처리 변경 의심) → **사람 확인 상자**(실패 테스트 `calculate_emptyItems_returnsZero`
    기대 0, 실제 null / 확인해 보실 곳 17행 / 선택지) → 종료 코드 3, 1,997 토큰. 기대값 자동 수정 0건
  - SC-001(`cta generate --class …OrderService --max-methods 4`): 4개 메서드 선정, 확인 항목 25개,
    1차 실행 실패(Mockito 오류 2건) → 2차 전체 통과 → 게이트 5종 통과(커버리지 100/100, 검출력 95%
    = 22개 중 21개) → OrderServiceTest에 +16 테스트(총 20개), 7분 54초 · 18,896 토큰, 정상 완료
  - SC-002(버그 수정 커밋): applyDiscount "버그 수정 98%"(근거: fix 메시지·> → >= ·시그니처 그대로),
    total은 주석만 → "의미 없는 변경 100%"(LLM 미호출). 재발 방지 테스트 +7 → **regression 게이트
    통과(수정 전 코드에서 실패함)**, 검출력 0% → 90%, 6분 27초, 정상 완료
  - SC-003 재개(`cta resolve --intended`): 실패 테스트 1건만 기대값 수정("기존 assert 9개 보존
    (사람 허용 1건 제외)"), 검출력 100%, 3분 52초 · 3,935 토큰, 판단 메모 저장
  - Docker 통합(재생 시나리오 + 게이트 ④⑤ 불변식) 2건 통과(158초), 단위 168건 통과, ruff 통과
- 발견·해결:
  - **[이슈: 도구 연동] 게이트웨이 응답 대기 120초 초과** — gpt-5가 메서드 4개짜리 테스트 파일
    (9,500자)을 만드는 데 100초+ 걸려 `TimeoutError`가 원문 스택으로 터짐. 상한 300초로 올리고
    `CTA_GATEWAY_TIMEOUT`으로 조정, 소켓 시간 초과를 `GatewayCallError`로 감싸 안내 문구 출력
  - **[이슈: 도구 연동] Neo4j 미기동 시 폴백이 질의 시점에 터짐** — 드라이버 생성은 접속 없이
    성공한다. 생성 직후 탐색 질의로 접속을 확인해 파싱 폴백으로 넘어가게 수정
  - **[이슈: 도구 연동] 생성자를 메서드로 오인** — 파서 정규식이 `public OrderService(…)`를 이름
    "OrderService"인 메서드로 잡아 선정 후보에 들어옴. 이름이 클래스와 같으면 생성자로 보고 제외
  - **[이슈: 프롬프트] 의도 분류가 "동작이 바뀐 것 같다"며 unclear로 도망감** — 리팩터링 커밋의
    diff에서 모델이 빈 리스트 처리 누락을 알아채고 unclear(87%)를 골라 질문 상자로 감. 프롬프트를
    "category는 작성자의 의도, 동작 보존 여부는 기존 테스트 실행이 판정한다 — 의심 지점은 evidence에
    적어라"로 바꾸자 refactor(90%) + 근거에 의심 지점 → 규칙표 escalate(시나리오 흐름). 질문 상자도
    테스트가 깨진 상태면 실패 상세·선택지를 같이 보여주도록 통일
  - Git Bash heredoc이 긴 파이썬 패치를 잘라먹음(unexpected EOF) — 패치는 파일로 써서 실행
  - **[이슈: 도구 연동] JaCoCo 실행 기록이 이전 실행분에 덧붙여짐** — Neo4j를 켜고 그래프 경로로
    SC-003을 돌리자 `PricingCalculator#calculate`의 검증 테스트가 `OrderServiceTest`로 나옴. 원인:
    jacoco.exec의 append 기본값(true)으로 직전 커버리지 게이트 실행의 기록이 그래프 실측에 섞임 —
    커버리지 게이트 수치도 부풀릴 수 있는 결함. `-Djacoco.append=false`로 매번 새로 기록
  - **[이슈: 도구 연동] 깨진 테스트 클래스는 COVERS가 비었음** — 리팩터링으로 실패 중인
    PricingCalculatorTest는 mvn이 report 단계 전에 멈춰 실행 기록이 없었다. "실행했는가"는 통과
    여부와 무관하므로 `-Dmaven.test.failure.ignore=true`로 리포트를 남긴다(통과 판정은 러너가 담당)


### 코드 그래프 실연결 실측 — Neo4j 경로로 SC-001/002/003 (2026-09-03)
- 구현: `cli/graph_access.py` — 접속 확인 질의 후 Neo4j면 실물, 아니면 파싱 폴백. generate의
  유사 테스트 검색(GraphCodeGraph.similar_tests)과 maintain의 검증 테스트 찾기(COVERS)가 공유.
  화면에 "코드 그래프(Neo4j 실측)" / "소스 파싱 폴백"을 표시
- 실측(cta graph --coverage → Neo4j, gpt-5, Docker):
  - 데모 그래프: 클래스 13, 메서드 65, 엣지 97(COVERS 포함). SC-001 `--max-methods 2`:
    delete·total 선정(20개 기존 참조 제외), 유사 테스트를 그래프에서 검색, 1차 통과, 게이트 5종 통과
    (검출력 4/4), +4 테스트(총 24), 5분 13초 · 8,874 토큰
  - SC-003: COVERS 실측으로 PricingCalculatorTest 발견 → 4건 중 1건 실패 → 리팩터링 86% → 사람 확인.
    "참고" 줄에 직전 resolve의 판단 메모가 나옴. `cta resolve --test-issue` 재개: 실패 테스트 1건만
    재작성(assertNull), 기존 assert 9개 보존, 검출력 100%, 4분 0초 · 4,516 토큰
- **[이슈: 재생] SC-001 결과를 apply하자 `cta demo` 재생이 깨짐** — 저장된 호출 기록은 요청 전문을
  대조하는데, 예제의 기존 테스트가 24개로 늘자 '비슷한 테스트' 본보기가 달라져 불일치. 예제 트리를
  바꾸면 `scripts/record_golden.py`로 기록을 다시 만든다(대본 모드, 비용 0) — 재생성 후 정상
- 산출물: 실행 로그를 그대로 PNG로 그리는 `scripts/render_capture.py`(스크린샷 대신 로그 기반 —
  캡처와 로그가 어긋날 일이 없다), 사용자 관점·데이터 흐름 관점 워크플로우 다이어그램 2종 추가

### 결함 점검 (기능 추가 없이) — 2026-09-03
- **[결함] 검증 테스트 클래스가 대상과 다른 패키지에 있으면 새 파일이 엉뚱한 곳에 생김** —
  maintain이 COVERS로 찾은 테스트 클래스 이름을 넘겨도 경로는 대상 패키지로만 계산해 "기존 파일에
  추가"가 조용히 실패. `locate_test_file`이 테스트 트리에서 이름으로 먼저 찾도록 수정 + 단위 테스트
- **[결함] 작성 루프 도중 예외(게이트웨이 시간 초과·Ctrl+C·Docker 오류)가 나면 생성물이 소스 트리에 남음** —
  복구가 정상 종료 경로에만 있었다. 예외 시에도 기존 파일은 원문으로, 새 파일은 삭제로 되돌린 뒤 다시 던진다
- 산출물 PoC구현.md를 README 구조와 제출 양식을 합쳐 재작성 — 개요(상황·명령 표, 원칙, 빠른 시작) →
  핵심 구현 내용(양식 2.1/2.2/2.3, 각 구현 기능·동작 원리·주요 기술) → 문제 해결·리서치 표(이슈 구분·원인·리서치·적용) →
  핵심 동작 검증(검증마다 입력·에이전트 동작·최종 결과) → 한계 → 문서 지도. 표 중심, 서술 최소
## 문제·리서치 로그

- **[이슈: 설계] 스킬의 ADR-0010 번호 충돌** — phase2 스킬이 예정한 ADR-0010
  (LangGraph 루프)을 LLM 백엔드 결정이 먼저 사용 → ADR-0012로 소급 기록, 번호
  주석 명시
- **[이슈: 도구 연동] COVERS의 귀속 단위** — JaCoCo는 실행 전체의 커버리지를
  주므로 테스트 "메서드"별 귀속은 메서드별 격리 실행이 필요해 비용이 큼.
  테스트 "클래스" 단위 실측으로 시작(알려진 한계로 계약에 기록). 메서드 단위가
  필요해지면 M7 하네스에서 비용 대비 효과를 측정 후 결정
- **[이슈: 도구 연동] 하위 폴더 프로젝트의 diff 경로 어긋남** — 대상 프로젝트가
  더 큰 git 저장소의 하위 폴더면 diff 경로가 저장소 루트 기준이라 메서드 매핑이
  전부 빗나가 클래스 단위로 뭉개짐. 리서치: git diff `--relative` 문서.
  해결: `--relative` 추가 + 중첩 저장소 회귀 테스트. 전후: 심볼 `Calculator` →
  `Calculator#add` 정확 매핑
- **[이슈: 캐시] JaCoCo 플러그인이 기존 캐시에 없음** — 준비 단계 예열에 jacoco
  goals를 포함시켜 해결. 기존 캐시는 삭제 후 재준비 필요(사용가이드에 반영 예정)

- **[이슈: 도구 연동] 제어문을 메서드로 오인하는 파싱 오탐** — 메서드 시그니처
  정규식의 반환 타입 부분이 공백만으로도 매칭돼 `if (x == 0) {`가 이름 "if"인
  메서드로 추출됨. 이름 조회만 하던 기존 경로에선 잠복했다가, 파일 모드의 전체
  열거 실측에서 `Calculator#if` 생성 시도로 드러남(gpt-5가 테스트까지 만들어 통과).
  해결: Java 키워드는 메서드 이름이 될 수 없다는 사실로 결정적 필터 + 회귀 테스트.
  전후: 계획 3건(유령 if 포함) → 2건(정확)

- **[이슈: 운영] 하네스 실행 중 `git add -A` 커밋이 생성 파일을 포획** — 벤치
  리셋(git clean)이 추적 파일을 못 지워 이후 케이스에 잔류(결과 유효성엔 영향
  없음 — 기준선에 일관 포함). 제거 커밋으로 정리. 재발 방지: 장시간 하네스 실행
  중에는 add -A 커밋 금지, 커밋 전 `git status examples/` 확인

## 개선 실험 후보 (수치 없는 개선 금지 — 하네스 전/후 비교로만)

1. 경계값 강조: 작성 프롬프트에 "경계값(같음/최대/최소)을 반드시 시험하라" 추가
   → truncate-boundary 검출 여부 + 전체 검출률 재측정
2. 모델 비교(ADR-0013): 같은 세트로 gpt-4.1 vs gpt-5 vs gpt-4.1-mini
   (검출률·시도 수·소요 비교 → 비용 대비 선택)

## 남은 스텁·후순위

- CALLS 엣지(확신도 포함) — 후순위, callers 쿼리는 안내 문장
- implementations·touches_outside 쿼리 — 후순위
- 증분 갱신(바뀐 파일만) — M5 변경 추출과 함께
- generate_test.py의 그래프 사용 옵션(현재 파싱 폴백 고정) — M5 파이프라인 배선 시
