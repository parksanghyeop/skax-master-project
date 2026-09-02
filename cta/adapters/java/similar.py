"""구조가 비슷한 기존 테스트 찾기 — SimilarTestFinder의 파싱 기반 최소본.

v4 4.1 쿼리 "비슷한 모양의 테스트는?"의 PoC 구현. 좋은 본보기의 조건은
"내용이 비슷"이 아니라 "모양이 비슷"(입력 개수, 예외 유무)이다(v4 5절).
그래프 DB 없이, 프로젝트의 기존 테스트를 파싱해 모양 거리로 고른다 —
2단계에서 Neo4j 쿼리로 교체될 자리다. 층: adapters/java.
"""

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import extract_methods, find_class_file, parse_methods, parse_target

# 프롬프트에 붙일 본보기 수. 많을수록 토큰만 늘고 효과가 줄어 2개로 제한(경험칙, 조정 가능).
MAX_EXAMPLES = 2


class ParsingCodeGraph:
    """그래프 DB 없이 동작하는 CodeGraph 구현 — 파싱 기반 폴백.

    similar_tests만 실응답(JavaSimilarTestFinder 위임)하고 나머지는 안내 문장.
    왜 남겨 두나: 그래프를 아직 빌드하지 않은 프로젝트·1회성 실행에서도
    파이프라인이 돌아야 하고, 저장된 LLM 호출 기록(대표 시나리오)의 재생
    호환도 이 구현이 보장한다.
    """

    def __init__(self, finder: "JavaSimilarTestFinder") -> None:
        self._finder = finder

    def answer(self, query: str, target: str) -> str:
        if query == "similar_tests":
            return self._finder.find(target)
        return (
            f"그래프 미구축: 쿼리 {query!r}는 build_graph 실행 후 답할 수 있다 — "
            "지금은 inspect_target을 쓰라"
        )


class JavaSimilarTestFinder:
    """대상 메서드와 모양이 닮은 기존 @Test 메서드를 찾아 발췌를 돌려준다."""

    def __init__(self, project: MavenProject) -> None:
        self._project = project

    def find(self, target: str) -> str:
        class_name, method_field = parse_target(target)
        wanted = parse_methods(method_field)
        class_file = find_class_file(self._project, class_name)
        if class_file is None or not wanted:
            return f"대상 없음: {target!r} — 'Class#method' 형식이 필요하다"
        # 메서드가 여럿이면 첫 메서드의 모양을 기준으로 본보기를 고른다(본보기는 스타일 참고용)
        target_methods = [
            m
            for m in extract_methods(class_file.read_text(encoding="utf-8"))
            if m.name == wanted[0]
        ]
        if not target_methods:
            return f"메서드 없음: {target!r}"
        shape = target_methods[0]

        # 흐름: 모든 테스트 파일의 @Test 메서드를 모아 → 모양 거리로 정렬 → 상위만 발췌
        candidates = []
        test_dir = self._project.test_source_dir
        if not test_dir.is_dir():
            return "기존 테스트 없음: 테스트 디렉터리가 없다"
        for path in sorted(test_dir.rglob("*.java")):
            source = path.read_text(encoding="utf-8")
            for m in extract_methods(source):
                if not m.is_test:
                    continue
                # 모양 거리: 파라미터 수 차이 + 예외 유무 불일치(1점).
                # 예외를 다루는 메서드에는 예외를 다루는 본보기가 더 유용하다는 가정.
                distance = abs(m.param_count - shape.param_count) + (
                    1 if m.uses_exception != shape.uses_exception else 0
                )
                candidates.append((distance, path.name, m))
        if not candidates:
            return "기존 테스트 없음: @Test 메서드를 찾지 못했다"
        candidates.sort(key=lambda c: (c[0], c[1], c[2].name))
        picked = candidates[:MAX_EXAMPLES]
        parts = [f"본보기 ({name}):\n{m.text}" for _, name, m in picked]
        return "\n\n".join(parts)
