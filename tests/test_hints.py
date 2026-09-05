"""오류 안내(cli/hints.py) — 설치 직후 만나는 실패 7상황마다 왜/할 일/명령이 나온다."""

from cta.adapters.java.maven import NotAMavenProjectError
from cta.cli.hints import find_hint, render_error
from cta.llm.gateway import GatewayCallError, GatewayConfigError
from cta.llm.metering import BudgetExceededError
from cta.llm.replay import CassetteError


class TestSevenSituations:
    def test_게이트웨이_설정_없음(self):
        text = render_error(
            GatewayConfigError("환경변수 CTA_GATEWAY_URL·CTA_GATEWAY_API_KEY가 필요하다")
        )
        assert "왜:" in text and ".env" in text and "copy .env.example .env" in text

    def test_게이트웨이_시간_초과(self):
        text = render_error(GatewayCallError("게이트웨이 응답 대기 초과 (deployment=gpt-5, 300초)"))
        assert "timeout_sec" in text and "--max-methods" in text

    def test_게이트웨이_기타_실패(self):
        hint = find_hint(GatewayCallError("게이트웨이 호출 실패 (deployment=gpt-5): refused"))
        assert hint is not None and "VPN" in hint.todo

    def test_저장된_호출_기록_없음(self):
        text = render_error(CassetteError("카세트 없음: x.json"))
        assert "record_golden.py --live" in text and "R7" in text

    def test_토큰_예산_초과(self):
        assert "max_tokens_per_run" in render_error(BudgetExceededError("토큰 예산 초과"))

    def test_pom_xml_없음_예외와_문구_둘_다(self):
        assert "--project" in render_error(NotAMavenProjectError("pom.xml이 없다: /x"))
        assert "--project" in render_error("pom.xml이 없다: /x")  # run_generation의 report 문구

    def test_docker_미실행_예외와_샌드박스_출력_둘_다(self):
        assert "docker info" in render_error(FileNotFoundError("[WinError 2] docker"))
        prepared = "준비 실패 (exit 1)\nerror during connect: ... docker API"
        assert "Docker Desktop" in render_error(prepared)


class TestRendering:
    def test_안내가_없는_예외는_디버그_방법을_알려준다(self):
        text = render_error(RuntimeError("알 수 없는 문제"))
        assert text.startswith("오류: 알 수 없는 문제") and "CTA_DEBUG=1" in text

    def test_안내가_없는_문구는_원문만_낸다(self):
        assert render_error("테스트 만들 메서드가 없다") == "오류: 테스트 만들 메서드가 없다"

    def test_출력_직전에_키를_가린다(self, monkeypatch):
        monkeypatch.setenv("CTA_GATEWAY_API_KEY", "atl-leaked-key-000000")
        text = render_error(GatewayCallError("호출 실패: atl-leaked-key-000000"))
        assert "atl-leaked-key-000000" not in text and "****" in text

    def test_사용자_중단(self):
        assert "되돌려졌다" in render_error(KeyboardInterrupt("사용자 중단"))

    def test_설정_파일_오류(self):
        assert "§9" in render_error(ValueError("cta.toml [retry]: 1 이상이어야 한다"))
