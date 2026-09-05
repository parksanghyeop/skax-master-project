# ADR-0019: 로컬 실행 모드 — `--fast`는 Docker 없이 이 PC의 Maven·JDK로 돈다 (R6의 명시적 완화)

- 상태: 승인 (2026-09-06). 사용자 요청 — "Docker로 실행하는 게 너무 오래 걸린다. 빠른 진행을 `--fast`로 넣고 싶다"

## 배경

Docker 샌드박스는 첫 실행에 이미지 + 의존성 캐시(go-offline) + 예열로 5분쯤, 이후 실행마다 컨테이너 기동과
오프라인 Maven으로 수십 초가 든다. 개발자가 자기 PC에서 자기 코드베이스에 반복해서 돌릴 때 이 비용이 체감상 가장 크다.
CLAUDE.md R6은 "샌드박스 밖에서 대상 코드 실행 금지 — 디버깅 목적이라도"다. 이 결정은 R6을 **사용자가 명시한 경우에
한해** 완화한다.

## 결정

1. **실행 장치 두 가지**: `docker`(기본, 격리) / `local`(이 PC의 Maven·JDK, 격리 없음). `sandbox/factory.py`
   `choose_runner(explicit, fast)` — 명시한 `--runner`가 이기고, 없으면 `--fast`일 때만 `local`
2. **`--fast`의 뜻이 바뀐다**: 이전 "커버리지·뮤테이션 게이트 생략"에 **"Docker 대신 로컬 실행"이 더해진다.**
   격리는 유지하고 게이트만 줄이려면 `--fast --runner docker`(CI 용도)
3. **`LocalSandbox`는 `DockerSandbox`와 같은 `run()` 시그니처**(`Sandbox` 프로토콜). 어댑터(runner·writer·coverage·
   mutation·gates)는 한 줄도 바뀌지 않는다. 차이는 셋: 이미지 무시 / 컨테이너 경로(`/work`, `/m2repo`)를 mounts로 호스트
   경로 번역 / `-o`와 `-Dmaven.repo.local=`을 제거(사용자의 `~/.m2`를 쓰고 없는 의존성은 Maven이 받게 함)
4. **로컬 모드에는 준비 단계가 없다.** `ensure_prepared`를 건너뛴다 — 속도의 원천
5. **유지되는 안전장치**: R5(빈 selector 거부 — 로컬에서도 `EmptySelectorError`), 테스트 폴더 밖 쓰기 금지(writer), 게이트
   6종의 판정 로직, 제안 보관(apply 전 소스 불변). 바뀌는 것은 "어디서 돌리나"뿐이다
6. **사용자가 알고 쓰게 한다**: 로컬 모드를 켜면 화면에 경고 한 줄(`LOCAL_MODE_WARNING`) — "생성된 테스트가 이 PC의
   JVM에서 격리 없이 실행된다. 신뢰하는 코드베이스에서만". `[3/4]` 줄에 `실행: local`, 결과 dict에 `runner`
7. **CLAUDE.md R6 갱신**: "기본값은 Docker 샌드박스. 사용자가 `--fast`/`--runner local`로 명시한 경우에만 로컬 실행
   (ADR-0019). 코드가 스스로 로컬로 폴백하지 않는다"
8. Maven이 PATH에 없으면 `'mvn'`을 담은 `FileNotFoundError` → 오류 안내(`cli/hints.py`) "Maven·JDK 설치 또는 `--runner docker`"

## 하지 않은 것

- Docker 실패 시 로컬로 자동 폴백 — 격리를 조용히 잃는 경로라 만들지 않는다
- 로컬 모드에서 네트워크 차단·마운트 통제 흉내 — 불가능하고 오해를 부른다. 경고로 대신한다
- `cta graph --coverage`, 골든 재생(`cta demo`)의 로컬화 — Docker 유지(측정·재생의 재현성)

## 검증

- 단위: `tests/test_local_sandbox.py` 8건 — 경로 번역(경계에서만), 플래그 제거, 선택 규칙(fast→local, 명시가 이김,
  모르는 이름 거부), 호스트 실행 인자·cwd, mvn 없음 안내
- 실기동(2026-09-06, 이 PC, Maven 3.9.11 + JDK 23, Docker 없음): `examples/evalbench`에서
  `JavaTestRunner(LocalSandbox).run("TextUtilTest")` **통과 6초**, `JavaTestWriter.write()` 컴파일 검사 **2초**,
  빈 selector `EmptySelectorError` 유지. 같은 작업이 Docker 경로에서는 첫 실행 3~5분이었다
- 미검증: `cta generate --fast` 전체(게이트웨이 필요), 로컬 모드에서 커버리지·뮤테이션 게이트(`--runner local` 단독)

## 결과

- 개발자 PC의 반복 실행이 분 단위에서 초 단위로 내려간다. 대신 격리를 잃는다 — 그래서 기본값이 아니다
- `--fast`의 의미 변경은 사용가이드·README·MCP 도구 설명에 같은 문장으로 적었다
