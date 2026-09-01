"""구조가 비슷한 기존 테스트 찾기 — SimilarTestFinder의 파싱 기반 최소본.

v4 4.1 쿼리 "비슷한 모양의 테스트는?"의 PoC 구현. 좋은 본보기의 조건은
"내용이 비슷"이 아니라 "모양이 비슷"(입력 개수, 예외 유무)이다(v4 5절).
그래프 DB 없이, 프로젝트의 기존 테스트를 파싱해 모양 거리로 고른다 —
2단계에서 Neo4j 쿼리로 교체될 자리다. 층: adapters/java.
"""

from adapters.java.maven import MavenProject
from adapters.java.parsing import extract_methods, find_class_file, parse_target

# 프롬프트에 붙일 본보기 수. 많을수록 토큰만 늘고 효과가 줄어 2개로 제한(경험칙, 조정 가능).
MAX_EXAMPLES = 2


class JavaSimilarTestFinder:
    """대상 메서드와 모양이 닮은 기존 @Test 메서드를 찾아 발췌를 돌려준다."""

    def __init__(self, project: MavenProject) -> None:
        self._project = project

    def find(self, target: str) -> str:
        class_name, method_name = parse_target(target)
        class_file = find_class_file(self._project, class_name)
        if class_file is None or not method_name:
            return f"대상 없음: {target!r} — 'Class#method' 형식이 필요하다"
        target_methods = [
            m
            for m in extract_methods(class_file.read_text(encoding="utf-8"))
            if m.name == method_name
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
