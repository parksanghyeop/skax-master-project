"""대표 검증 시나리오 배선 — "OrderService#applyDiscount에 새 테스트 생성"의 단일 정의.

기록 생성 스크립트(scripts/record_golden.py)와 재생 테스트(tests/test_golden_case_docker.py),
`cta demo`가 이 모듈 하나를 공유한다 — 프롬프트 재료가 조금이라도 어긋나면 저장된 LLM
호출 기록의 재생이 실패하므로, 정의를 한 곳에 모은다. 대상 예제는 Spring Boot 주문
CRUD 앱(examples/demo)이고, 재생은 작성 서브그래프(정보 수집→생성→컴파일→실행→품질)만
돈다. 테스트 클래스는 새 파일(OrderServiceDiscountTest)로 두어 반복 실행 후 지울 수 있게 한다.
"""

from pathlib import Path

from cta.adapters.fake import ScriptedUserGate
from cta.adapters.java.inspector import JavaSourceInspector
from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.quality import AssertCountChecker
from cta.adapters.java.runner import JavaTestRunner
from cta.adapters.java.similar import JavaSimilarTestFinder, ParsingCodeGraph
from cta.adapters.java.writer import JavaTestWriter
from cta.core.writer_graph import WriterPorts, WriterState
from cta.llm.client import ChatMessage, ChatResponse
from cta.llm.generation import PromptedGenerator
from cta.sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parents[2]  # cta/evals/ → 리포 루트
DEMO_PROJECT = REPO_ROOT / "examples" / "demo"
M2_CACHE = DEMO_PROJECT / ".cta" / "m2repo"  # CLI(generate/maintain)와 같은 캐시를 공유
CASSETTE = REPO_ROOT / "cta" / "evals" / "golden" / "generate_discount_test.json"

TARGET = "OrderService#applyDiscount"
SELECTOR = "OrderServiceDiscountTest"
TEST_PATH = (
    DEMO_PROJECT
    / "src"
    / "test"
    / "java"
    / "com"
    / "example"
    / "demo"
    / "order"
    / "OrderServiceDiscountTest.java"
)
INSTRUCTION = (
    "OrderService#applyDiscount에 대한 새 테스트를 만들라. "
    "GOLD 등급의 임계금액 경계(같음·미만), 프로모션 여부, null 입력과 음수 금액 예외를 시험하라. "
    f"테스트 클래스 이름은 {SELECTOR}, 패키지는 com.example.demo.order."
)
LANGUAGE = "Java"
FRAMEWORK = "JUnit 5"
STYLE_NOTES = (
    "테스트 메서드 이름은 대상_상황_기대 형식(예: create_validInput_savesNewOrder). "
    "static import로 Assertions를 쓰고, 저장소는 Mockito mock으로 만든다."
)
# 대본 기록 시 기본 모델(deployment) 이름. 재생 시에는 기록에 적힌 모델을 그대로
# 쓴다(cassette_model 참조) — 모델 변경 후 다시 기록해도 코드 수정이 없게 하기 위해서.
SCRIPTED_MODEL = "gpt-4.1"

# 대본 응답: 게이트웨이 미접속 환경에서도 기록을 만들 수 있게 둔 고정 답.
SCRIPTED_ANSWER = """\
```java
package com.example.demo.order;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

import com.example.demo.customer.Customer;
import com.example.demo.customer.Grade;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderServiceDiscountTest {

    private final OrderService service = new OrderService(mock(OrderRepository.class));

    private static Order orderOf(String amount) {
        return Order.builder().customerName("kim").amount(new BigDecimal(amount)).build();
    }

    @Test
    void applyDiscount_goldAtThreshold_appliesGoldRate() {
        Customer gold = new Customer("kim", Grade.GOLD);
        BigDecimal result = service.applyDiscount(orderOf("10000"), gold, false);
        assertEquals(0, new BigDecimal("8500").compareTo(result));
    }

    @Test
    void applyDiscount_goldBelowThreshold_noGoldRate() {
        Customer gold = new Customer("kim", Grade.GOLD);
        BigDecimal result = service.applyDiscount(orderOf("9999"), gold, false);
        assertEquals(0, new BigDecimal("9999").compareTo(result));
    }

    @Test
    void applyDiscount_promo_appliesPromoRate() {
        Customer basic = new Customer("kim", Grade.BASIC);
        BigDecimal result = service.applyDiscount(orderOf("1000"), basic, true);
        assertEquals(0, new BigDecimal("950").compareTo(result));
    }

    @Test
    void applyDiscount_noPromoBasic_returnsAmount() {
        Customer basic = new Customer("kim", Grade.BASIC);
        BigDecimal result = service.applyDiscount(orderOf("1000"), basic, false);
        assertEquals(0, new BigDecimal("1000").compareTo(result));
    }

    @Test
    void applyDiscount_nullOrder_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> service.applyDiscount(null, new Customer("kim", Grade.GOLD), false));
    }

    @Test
    void applyDiscount_nullCustomer_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> service.applyDiscount(orderOf("1000"), null, false));
    }

    @Test
    void applyDiscount_negativeAmount_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> service.applyDiscount(orderOf("-1"), new Customer("kim", Grade.GOLD), false));
    }
}
```
"""


def cassette_model() -> str:
    """기록에 적힌 모델 이름을 돌려준다. 기록이 없으면 대본 기본값.

    재생은 요청(모델 포함)을 기록과 대조하므로, 재생 측 모델은 반드시
    기록 시점의 모델과 같아야 한다 — 그 원천은 기록 파일 자신이다.
    """
    if CASSETTE.is_file():
        import json

        entries = json.loads(CASSETTE.read_text(encoding="utf-8"))
        if entries:
            return entries[0]["request"]["model"]
    return SCRIPTED_MODEL


class ScriptedLlm:
    """기록용 대본 클라이언트 (LlmClient 구현) — 요청과 무관하게 대본을 돌려준다."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)

    def chat(self, messages: list[ChatMessage], model: str) -> ChatResponse:
        return ChatResponse(content=self._answers.pop(0))


def make_ports(llm_client, model: str | None = None) -> WriterPorts:
    """실물 어댑터 + 주어진 LLM 클라이언트로 서브그래프 포트를 조립한다.

    llm_client 자리에 RecordingClient(기록)나 ReplayClient(재생)를 꽂는다.
    model: 기록 시에는 사용할 모델을 명시하고, 재생 시에는 생략(기록값 사용).
    """
    project = detect_maven_project(DEMO_PROJECT)
    sandbox = DockerSandbox()
    return WriterPorts(
        inspector=JavaSourceInspector(project),
        # 파싱 기반 CodeGraph: 저장된 호출 기록의 재생 호환(비슷한 테스트 답이 동일)을 보장한다
        graph=ParsingCodeGraph(JavaSimilarTestFinder(project)),
        writer=JavaTestWriter(project, sandbox, M2_CACHE),
        runner=JavaTestRunner(project, sandbox, M2_CACHE),
        checker=AssertCountChecker(project),
        gate=ScriptedUserGate(),  # 재생·시연은 자동 "계속" 스텁
        generator=PromptedGenerator(
            llm_client, model or cassette_model(), LANGUAGE, FRAMEWORK, STYLE_NOTES
        ),
    )


def initial_state() -> WriterState:
    return {
        "instruction": INSTRUCTION,
        "target": TARGET,
        "test_path": str(TEST_PATH),
        "selector": SELECTOR,
        "context": "",
        "test_code": "",
        "write_result": "",
        "last_run": "",
        "prev_run": "",
        "attempts": 0,
        "quality": "",
        "report": "",
        "status": "working",
        "extra_context": "",
        "history": [],
    }
