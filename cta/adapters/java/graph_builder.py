"""Java 소스 → 코드 그래프 노드·엣지 변환 (M4).

언어를 아는 쪽(여기)이 그래프를 채우고, graph/ 계층은 저장·질의만 한다.
확정 엣지 중 정적으로 읽히는 2종(DECLARES, CREATES)을 만든다 —
COVERS(검증한다)는 커버리지 실측이 근거라 coverage.py가 따로 만든다.
"""

import re

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import extract_methods
from cta.graph.model import (
    EDGE_CREATES,
    EDGE_DECLARES,
    NODE_CLASS,
    NODE_METHOD,
    SNIPPET_MAX_CHARS,
    GraphEdge,
    GraphNode,
)

# "new 클래스이름(" — 프로젝트 안 클래스만 CREATES로 인정한다(외부 라이브러리 생성은 잡음)
_NEW_EXPR = re.compile(r"\bnew\s+(\w+)\s*[(<]")


def build_graph(project: MavenProject) -> tuple[list[GraphNode], list[GraphEdge]]:
    """프로젝트 전체를 파싱해 (노드, 엣지)를 만든다.

    출력: Class·Method 노드와 DECLARES·CREATES 엣지. 파싱 실패한 파일·메서드는
      조용히 건너뛴다(그래프는 보조 정보 — 없는 것보다 틀린 확신이 위험하다).
    """
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    class_names: set[str] = set()
    # (메서드 key, 본문) — CREATES는 클래스 목록이 다 모인 뒤 2차로 계산한다
    method_bodies: list[tuple[str, str]] = []

    roots = [project.root / "src" / "main" / "java", project.test_source_dir]
    for root, in_test_tree in ((roots[0], False), (roots[1], True)):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.java")):
            class_name = path.stem
            source = path.read_text(encoding="utf-8", errors="replace")
            class_names.add(class_name)
            nodes.append(
                GraphNode(
                    kind=NODE_CLASS,
                    key=class_name,
                    props={"is_test": in_test_tree},
                )
            )
            for m in extract_methods(source):
                key = f"{class_name}#{m.name}"
                nodes.append(
                    GraphNode(
                        kind=NODE_METHOD,
                        key=key,
                        props={
                            "class_name": class_name,
                            "name": m.name,
                            "param_count": m.param_count,
                            "uses_exception": m.uses_exception,
                            # 테스트 판정: @Test 어노테이션이 정답. 테스트 트리의 보통
                            # 메서드(헬퍼)는 본보기 후보가 아니므로 is_test로 치지 않는다
                            "is_test": m.is_test,
                            "snippet": m.text[:SNIPPET_MAX_CHARS],
                        },
                    )
                )
                edges.append(GraphEdge(kind=EDGE_DECLARES, src=class_name, dst=key))
                method_bodies.append((key, m.text))

    for method_key, body in method_bodies:
        for created in set(_NEW_EXPR.findall(body)):
            if created in class_names:
                edges.append(GraphEdge(kind=EDGE_CREATES, src=method_key, dst=created))

    return _dedupe(nodes), sorted(set(edges), key=lambda e: (e.kind, e.src, e.dst))


def _dedupe(nodes: list[GraphNode]) -> list[GraphNode]:
    # 같은 key가 여러 번 나오면(중첩 클래스 파싱 한계 등) 먼저 나온 것을 남긴다
    seen: dict[str, GraphNode] = {}
    for n in nodes:
        seen.setdefault(n.key, n)
    return list(seen.values())
