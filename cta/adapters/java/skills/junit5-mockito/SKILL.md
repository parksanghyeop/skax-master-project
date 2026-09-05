---
name: junit5-mockito
description: Mockito로 의존 객체를 대체하는 JUnit 5 단위 테스트 관례 — 대상이 저장소·인터페이스에 의존할 때
when: 재료 수집이 "mock 사용"으로 판정한 의존 객체가 하나 이상 있을 때
---
- 클래스에 `@ExtendWith(MockitoExtension.class)`. 의존 객체는 `@Mock`, 대상은 `@InjectMocks`.
  생성자 주입이면 `@InjectMocks`가 파라미터 타입으로 맞춰 넣는다 — 같은 타입이 둘이면 직접 생성한다.
- 스텁은 `when(repo.findById(1L)).thenReturn(Optional.of(order))`. 반환이 `Optional`이면
  `Optional.empty()`로 "없음" 경로 테스트도 만든다.
- 호출 검증은 `verify(repo).save(any(Order.class))`. 호출이 없어야 하면 `verify(repo, never()).save(any())`.
- MockitoExtension은 strict stubs다 — 테스트가 쓰지 않는 stub은 `UnnecessaryStubbingException`으로 실패한다.
  각 테스트 메서드 안에 그 테스트가 쓰는 stub만 둔다. `@BeforeEach`에 공통 stub을 두지 않는다.
- 흔한 컴파일·실행 오류: matcher(`any()`, `eq()`)와 실제 값을 한 호출에 섞기 — 하나를 matcher로 쓰면 전부
  matcher(`eq(값)`)로. `import static org.mockito.Mockito.*;`와
  `import static org.mockito.ArgumentMatchers.*;` 둘 다 필요하다.
- 값 객체(builder·record·표준 타입)는 mock하지 않고 직접 만든다 — 재료의 "직접 생성" 목록을 따른다.
