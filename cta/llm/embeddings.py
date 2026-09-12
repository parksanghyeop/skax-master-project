"""임베딩(문장 → 숫자 벡터) 클라이언트 — 판단 메모의 "비슷한 상황" 검색용 (ADR-0026 D3, v4 4.1 ④).

임베딩 검색은 **자연어에만** 쓴다(판단 메모의 상황 요약·커밋 메시지). 코드 검색에는 쓰지 않는다 —
"누가 호출하나"는 그래프(CALLS)가 답한다. 게이트웨이 경로는 chat과 같은 Azure OpenAI 호환 형식
(`/openai/deployments/{deployment}/embeddings`)이고, 기본 deployment는 text-embedding-3-small
(ADR-0013). 임베딩 호출도 LLM 호출이므로 기록·재생 장치를 같이 둔다(R7). 층: llm.
"""

import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Protocol
from urllib.error import URLError

from cta.llm.gateway import (
    DEFAULT_API_VERSION,
    ENV_API_KEY,
    ENV_API_VERSION,
    ENV_BASE_URL,
    GatewayCallError,
    GatewayConfigError,
)
from cta.llm.replay import CassetteError

ENV_EMBEDDING_MODEL = "CTA_EMBEDDING_MODEL"  # 임베딩 deployment 이름. 미설정 시 기본값
# 게이트웨이 제공 목록(text-embedding-3-large/small, ada-002) 중 1차 후보 — ADR-0013 결정 3
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
# 임베딩은 짧은 글 한 건이라 chat보다 훨씬 빠르다 — 응답 대기 상한(초). 조정: CTA_GATEWAY_TIMEOUT
REQUEST_TIMEOUT_SECONDS = 60


class EmbeddingClient(Protocol):
    """문장 목록을 벡터 목록으로 바꾼다.

    입력: texts 임베딩할 글(순서 유지), model 게이트웨이 deployment 이름.
    출력: texts와 같은 순서·길이의 벡터 목록.
    실패 시 동작: 구현별 예외 — 게이트웨이 오류(GatewayCallError), 기록 없음(CassetteError).
    """

    def embed(self, texts: list[str], model: str) -> list[list[float]]: ...


def build_embeddings_url(base_url: str, deployment: str, api_version: str) -> str:
    """embeddings 요청 URL (Azure OpenAI 호환 경로). 순수 함수 — 네트워크 없이 테스트한다."""
    return (
        f"{base_url.rstrip('/')}/openai/deployments/{deployment}"
        f"/embeddings?api-version={api_version}"
    )


def build_embeddings_payload(texts: list[str]) -> dict:
    """요청 본문. 모델 선택은 URL(deployment)이 담당한다."""
    return {"input": list(texts)}


def parse_embeddings(data: dict, expected: int) -> list[list[float]]:
    """응답의 data[*].embedding을 index 순으로 돌려준다. 개수가 다르면 GatewayCallError."""
    try:
        rows = sorted(data["data"], key=lambda r: int(r.get("index", 0)))
        vectors = [[float(x) for x in r["embedding"]] for r in rows]
    except (KeyError, TypeError, ValueError) as e:
        raise GatewayCallError(f"임베딩 응답 형식 이상: 최상위 키 {sorted(data)[:10]}") from e
    if len(vectors) != expected:
        raise GatewayCallError(f"임베딩 응답 개수 불일치: 요청 {expected}, 응답 {len(vectors)}")
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    """코사인 유사도(-1~1). 영벡터·길이 불일치는 0.0 — 검색에서 "닮지 않음"으로 취급된다.

    순수 파이썬인 이유: 메모는 프로젝트당 수십 건이라 numpy·벡터 DB가 필요 없다(ADR-0026 D3).
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class GatewayEmbeddingClient:
    """게이트웨이에 embeddings 요청을 보내는 실호출 클라이언트 (EmbeddingClient 구현).

    실패 시 동작: 환경변수 없음 → GatewayConfigError(생성 시점),
      호출 실패·형식 이상 → GatewayCallError.
    """

    def __init__(self, timeout: int | None = None) -> None:
        base_url = os.environ.get(ENV_BASE_URL)
        api_key = os.environ.get(ENV_API_KEY)
        if not base_url or not api_key:
            raise GatewayConfigError(
                f"환경변수 {ENV_BASE_URL}·{ENV_API_KEY}가 필요하다 — "
                ".env 또는 환경변수로만(ADR-0011)"
            )
        self._base_url = base_url
        self._api_key = api_key
        self._api_version = os.environ.get(ENV_API_VERSION) or DEFAULT_API_VERSION
        self._timeout = timeout or REQUEST_TIMEOUT_SECONDS

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        request = urllib.request.Request(
            build_embeddings_url(self._base_url, model, self._api_version),
            data=json.dumps(build_embeddings_payload(texts)).encode("utf-8"),
            headers={"Content-Type": "application/json", "api-key": self._api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            # 키가 오류 문구에 섞여 나가지 않도록 원인만 요약한다(v4 6.6)
            raise GatewayCallError(f"임베딩 호출 실패 (deployment={model}): {e.reason}") from e
        except (TimeoutError, OSError) as e:
            raise GatewayCallError(f"임베딩 응답 대기 초과 (deployment={model}): {e}") from e
        return parse_embeddings(data, len(texts))


def _entry_key(model: str, text: str) -> str:
    """기록 대조 키 — 같은 글은 같은 벡터이므로 순서가 아니라 (모델, 글)로 찾는다."""
    return json.dumps([model, text], ensure_ascii=False)


class RecordingEmbeddingClient:
    """실제 클라이언트를 감싸 (모델, 글) → 벡터를 파일에 누적 저장한다."""

    def __init__(self, inner: EmbeddingClient, cassette_path: str | Path) -> None:
        self._inner = inner
        self._path = Path(cassette_path)
        self._entries: dict[str, list[float]] = {}
        if self._path.is_file():  # 이어서 기록 — 이미 있는 글은 다시 부르지 않는다
            self._entries = json.loads(self._path.read_text(encoding="utf-8"))

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        missing = [t for t in texts if _entry_key(model, t) not in self._entries]
        if missing:
            for text, vector in zip(missing, self._inner.embed(missing, model), strict=True):
                self._entries[_entry_key(model, text)] = vector
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._entries, ensure_ascii=False), encoding="utf-8")
        return [self._entries[_entry_key(model, t)] for t in texts]


class ReplayEmbeddingClient:
    """기록 파일만으로 답한다 — 실호출 능력이 없다. 없는 글은 CassetteError(폴백 금지, R7)."""

    def __init__(self, cassette_path: str | Path) -> None:
        self._path = Path(cassette_path)
        if not self._path.is_file():
            raise CassetteError(
                f"임베딩 기록 없음: {self._path} — 재생 모드는 실호출로 폴백하지 않는다"
            )
        self._entries: dict[str, list[float]] = json.loads(self._path.read_text(encoding="utf-8"))

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        vectors = []
        for text in texts:
            key = _entry_key(model, text)
            if key not in self._entries:
                raise CassetteError(f"임베딩 기록에 없는 글 (deployment={model}): {text[:80]!r}")
            vectors.append(self._entries[key])
        return vectors
