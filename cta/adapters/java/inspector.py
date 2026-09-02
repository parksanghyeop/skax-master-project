"""Java용 SourceInspector 구현 — 도구 inspect_target의 실물 뒷단.

대상 클래스 파일을 찾아 소스를 돌려준다. 대상은 "Class", "Class#method",
"Class#m1,m2"(메서드 여럿 — 시나리오 SC-001의 클래스당 테스트 하나) 모두 받는다.
파일 전체를 주고 길이 상한은 도구 층(clip)에 맡긴다. 층: adapters/java.
"""

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import extract_methods, find_class_file, parse_methods, parse_target


class JavaSourceInspector:
    """MavenProject 안에서 대상 식별자를 조사한다."""

    def __init__(self, project: MavenProject) -> None:
        self._project = project

    def inspect(self, target: str) -> str:
        class_name, method_field = parse_target(target)
        path = find_class_file(self._project, class_name)
        if path is None:
            return f"대상 없음: {target!r} — 클래스 {class_name!r} 파일을 찾지 못했다"
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(self._project.root)
        wanted = parse_methods(method_field)
        if wanted:
            names = [m.name for m in extract_methods(source)]
            missing = [w for w in wanted if w not in names]
            if missing:
                return f"메서드 없음: {missing} in {class_name}. {class_name}의 메서드: {names}"
            # 메서드만 주면 모델이 필드·import를 몰라 헤매므로 파일 전체를 함께 준다
            return f"파일: {rel}\n대상 메서드 {', '.join(wanted)} 발견 (파일 전체):\n{source}"
        return f"파일: {rel}\n{source}"
