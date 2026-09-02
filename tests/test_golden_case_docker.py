"""M3 관문 골든 케이스 — 실제 Docker 필요 (marker: docker).

카세트 재생(LLM 비용 0) + 실물 어댑터로 서브그래프를 끝까지 돌린다:
정보 수집 → 코드 생성(재생) → 파일 쓰기+컴파일 → 네트워크 차단 실행 → 품질 확인.
사전 조건: 데모 캐시(examples/demo/.cta/m2repo)가 준비돼 있어야 한다 (pytest -m docker로
test_java_adapter_docker가 먼저 채운다).
"""

import pytest

from cta.core.writer_graph import build_writer_graph
from cta.evals import golden_case as gc
from cta.llm.replay import ReplayClient


@pytest.mark.docker
def test_M3_관문_카세트_재생으로_테스트_생성부터_샌드박스_통과까지():
    try:
        ports = gc.make_ports(ReplayClient(gc.CASSETTE))
        final = build_writer_graph(ports).invoke(gc.initial_state())

        assert final["status"] == "passed", f"최종 상태: {final['status']}\n{final}"
        # 시도 횟수·테스트 개수는 녹음된 모델에 따라 다를 수 있어 고정하지 않는다
        assert final["last_run"].startswith("통과"), final["last_run"]
        assert "Tests run:" in final["last_run"]
        assert final["quality"].startswith("통과"), final["quality"]
        assert gc.TEST_PATH.is_file()  # 테스트 폴더 안에 실제로 쓰였다
    finally:
        # 생성물 정리 — 골든 케이스는 반복 실행 가능해야 한다(기준선·중복 클래스 오염 방지)
        gc.TEST_PATH.unlink(missing_ok=True)
