"""임베딩 클라이언트·기록 재생·판단 메모 하이브리드 검색의 단위 테스트 (ADR-0026 D3).

네트워크 없이 돈다 — 게이트웨이 요청·응답은 순수 함수로, 검색은 Fake 벡터로 검증한다.
불변식(메모가 규칙표를 우회 못함)은 tests/test_maintain_core.py TestMemosCannotBypassRules.
"""

import json

import pytest

from cta.adapters.java.maven import detect_maven_project
from cta.cli.memos import (
    MAX_SHOWN,
    SIMILARITY_MIN,
    Memo,
    find_similar,
    list_memos,
    save_memo,
    situation_text,
)
from cta.llm.config import make_embedding_client
from cta.llm.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    RecordingEmbeddingClient,
    ReplayEmbeddingClient,
    build_embeddings_payload,
    build_embeddings_url,
    cosine,
    parse_embeddings,
)
from cta.llm.gateway import ENV_API_KEY, ENV_BASE_URL, GatewayCallError
from cta.llm.replay import CassetteError


class FakeEmbedder:
    """글의 앞 글자로 벡터를 정하는 가짜 — 같은 글은 같은 벡터, 호출 기록을 남긴다."""

    def __init__(self, table: dict[str, list[float]]):
        self._table = table
        self.calls: list[list[str]] = []

    def embed(self, texts, model):
        self.calls.append(list(texts))
        return [self._table[t] for t in texts]


class TestGatewayPureFunctions:
    def test_URL은_deployment_경로와_api_version을_가진다(self):
        url = build_embeddings_url("https://gw.example/", "text-embedding-3-small", "2024-12-01")
        assert url == (
            "https://gw.example/openai/deployments/text-embedding-3-small"
            "/embeddings?api-version=2024-12-01"
        )

    def test_본문은_input_목록이고_응답은_index_순으로_정렬된다(self):
        assert build_embeddings_payload(["a", "b"]) == {"input": ["a", "b"]}
        data = {
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        }
        assert parse_embeddings(data, 2) == [[1.0, 0.0], [0.0, 1.0]]

    def test_응답_개수나_형식이_이상하면_GatewayCallError(self):
        with pytest.raises(GatewayCallError, match="개수"):
            parse_embeddings({"data": [{"index": 0, "embedding": [1.0]}]}, 2)
        with pytest.raises(GatewayCallError, match="형식"):
            parse_embeddings({"error": "x"}, 1)


class TestCosine:
    def test_같은_방향은_1_직교는_0_영벡터는_0(self):
        assert cosine([1.0, 2.0], [2.0, 4.0]) == pytest.approx(1.0)
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
        assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
        assert cosine([1.0], [1.0, 2.0]) == 0.0  # 길이 불일치도 "닮지 않음"


class TestRecordReplay:
    def test_기록한_벡터를_재생하고_없는_글은_거부한다(self, tmp_path):
        cassette = tmp_path / "emb.json"
        inner = FakeEmbedder({"안녕": [1.0, 0.0], "잘가": [0.0, 1.0]})
        recorder = RecordingEmbeddingClient(inner, cassette)
        assert recorder.embed(["안녕", "잘가"], "m") == [[1.0, 0.0], [0.0, 1.0]]
        assert recorder.embed(["안녕"], "m") == [[1.0, 0.0]]
        assert inner.calls == [["안녕", "잘가"]]  # 이미 기록된 글은 다시 부르지 않는다
        replayer = ReplayEmbeddingClient(cassette)
        assert replayer.embed(["잘가", "안녕"], "m") == [[0.0, 1.0], [1.0, 0.0]]
        with pytest.raises(CassetteError):
            replayer.embed(["안녕"], "다른모델")  # 모델도 대조 키에 들어간다
        with pytest.raises(CassetteError):
            replayer.embed(["모르는 글"], "m")

    def test_기록_파일이_없으면_재생은_실패한다_폴백_없음(self, tmp_path):
        with pytest.raises(CassetteError):
            ReplayEmbeddingClient(tmp_path / "없음.json")

    def test_기록에는_모델과_글과_벡터만_있다(self, tmp_path):
        cassette = tmp_path / "emb.json"
        RecordingEmbeddingClient(FakeEmbedder({"a": [0.5]}), cassette).embed(["a"], "m")
        raw = json.loads(cassette.read_text(encoding="utf-8"))
        assert raw == {json.dumps(["m", "a"], ensure_ascii=False): [0.5]}


class TestMakeEmbeddingClient:
    def test_게이트웨이_설정이_없으면_None이다(self, tmp_path, monkeypatch):
        monkeypatch.delenv(ENV_BASE_URL, raising=False)
        monkeypatch.delenv(ENV_API_KEY, raising=False)
        assert make_embedding_client(tmp_path / ".env") is None

    def test_설정이_있으면_기본_deployment로_클라이언트를_만든다(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ENV_BASE_URL, "https://gw.example")
        monkeypatch.setenv(ENV_API_KEY, "test-key")
        monkeypatch.delenv("CTA_EMBEDDING_MODEL", raising=False)
        client, model = make_embedding_client(tmp_path / ".env")
        assert model == DEFAULT_EMBEDDING_MODEL and hasattr(client, "embed")


def _project(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    return detect_maven_project(tmp_path)


def _memo(target, note, embedding=None, created="2026-09-01T00:00:00"):
    return Memo(target, "refactor", "intended", note, created, situation=note, embedding=embedding)


class TestSituationText:
    def test_커밋_메시지_첫_줄과_대상과_분석만_담고_코드는_없다(self):
        text = situation_text("fix: 간헐적 실패 수정\n\n본문", "OrderService#pay", "재시도 경계")
        assert (
            text
            == "커밋 메시지: fix: 간헐적 실패 수정 / 변경 대상 OrderService.pay / 분석: 재시도 경계"
        )
        assert situation_text("", "A#b") == "변경 대상 A.b"


class TestHybridMemoSearch:
    def test_이름_일치를_먼저_두고_빈_자리를_코사인_상위로_채운다(self, tmp_path):
        project = _project(tmp_path)
        save_memo(project, _memo("Calc#add", "같은 메서드", embedding=[0.0, 1.0]))
        save_memo(project, _memo("Other#flaky", "간헐적 실패 대응", embedding=[1.0, 0.0]))
        save_memo(project, _memo("Other#unrelated", "무관", embedding=[0.0, -1.0]))
        query = [1.0, 0.1]  # "flaky 대응"과 닮았고 "무관"과는 반대
        found = find_similar(project, "Calc#add", query)
        assert [m.note for m in found] == ["같은 메서드", "간헐적 실패 대응"]

    def test_기준치_아래는_붙이지_않고_벡터가_없으면_이름_일치만이다(self, tmp_path):
        project = _project(tmp_path)
        save_memo(project, _memo("Other#a", "약간 닮음", embedding=[1.0, 2.0]))
        save_memo(project, _memo("Other#b", "구 메모 — 벡터 없음"))
        weak = [2.0, -0.9]  # 코사인 ≈ 0.09 < SIMILARITY_MIN
        assert find_similar(project, "Calc#x", weak) == []
        assert find_similar(project, "Calc#x", None) == []
        assert 0.0 < SIMILARITY_MIN < 1.0

    def test_상한은_그대로_3건이다(self, tmp_path):
        project = _project(tmp_path)
        for i in range(5):
            save_memo(project, _memo(f"Other#m{i}", f"{i}", embedding=[1.0, float(i) * 0.01]))
        assert len(find_similar(project, "Calc#x", [1.0, 0.0])) == MAX_SHOWN

    def test_구_형식_메모_파일도_읽힌다(self, tmp_path):
        project = _project(tmp_path)
        d = tmp_path / ".cta" / "memos"
        d.mkdir(parents=True)
        (d / "20260101-000000-000000-00.json").write_text(
            json.dumps(
                {
                    "target": "Calc#add",
                    "category": "bug_fix",
                    "decision": "proceed",
                    "note": "옛 메모",
                    "created_at": "2026-01-01T00:00:00",
                }
            ),
            encoding="utf-8",
        )
        memo = list_memos(project)[0]
        assert memo.situation == "" and memo.embedding is None
        assert find_similar(project, "Calc#add", [1.0, 0.0]) == [memo]
