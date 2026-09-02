# examples/demo — Spring Boot 주문 CRUD 예제 (시나리오 실험대)

`docs/제출자료/시나리오수립.md`의 SC-001~SC-004를 재현하는 대상 프로젝트다.
Spring Boot 3.3 + Spring Data JPA + H2, Maven 단일 모듈, JUnit 5 + Mockito.

## 구성

| 파일 | 역할 | 시나리오에서의 자리 |
|---|---|---|
| `order/OrderService.java` | 주문 CRUD + 할인·총액 계산 | SC-001 대상(테스트 없는 메서드 다수), SC-002 버그 수정 대상(`applyDiscount`) |
| `order/OrderRepository.java` | JPA 저장소 인터페이스 | 재료 수집이 "mock 사용"으로 판단하는 예 |
| `order/Order.java` | 엔티티 + `Order.builder()` | "직접 생성 (builder 사용)"의 예 |
| `customer/Customer.java` | 값만 담는 객체 | "직접 생성 (값만 담는 객체)"의 예 |
| `pricing/PricingCalculator.java` | 품목 합계 계산 | SC-003 리팩터링(스트림 전환) 대상 |
| `order/OrderServiceTest.java` | 기존 테스트 4개 (Mockito) | 팀 스타일 본보기. `applyDiscount`·`total` 등은 일부러 없다 |
| `pricing/PricingCalculatorTest.java` | 기존 테스트 4개 | 리팩터링이 동작을 바꾸면 깨진다 |

## 시나리오 재현

```powershell
# SC-001 — 테스트 없는 클래스에 테스트 생성 (이 폴더에서)
cta generate --class com.example.demo.order.OrderService --max-methods 4
cta diff
cta apply

# SC-002 / SC-003 — 커밋 범위가 필요하므로 임시 폴더에 독립 저장소를 만든다
python ..\..\scripts\demo_scenarios.py bugfix   C:\tmp\cta-sc002   # v1(버그) → "fix:" 커밋
python ..\..\scripts\demo_scenarios.py refactor C:\tmp\cta-sc003   # 스트림 리팩터링 커밋(빈 목록 처리 누락)
cd C:\tmp\cta-sc002; cta maintain --diff HEAD~1                    # 재발 방지 테스트 + 수정 전 코드 검증
cd C:\tmp\cta-sc003; cta maintain --diff HEAD~1                    # 리팩터링인데 실패 → 사람 확인 후 멈춤
cta resolve --intended    # 또는 --test-issue — 저장된 지점부터 재개
```

`.env`(게이트웨이 주소·키)는 이 폴더에 두고 커밋하지 않는다. 최초 실행 시 의존성 준비
(Spring Boot 다운로드 + 예열)에 5~6분 걸리고 `.cta/m2repo`에 캐시된다.
