"""Java용 SourceInspector 구현 — 도구 inspect_target의 실물 뒷단.

대상 클래스 파일을 찾아 소스를 돌려준다. PoC 프로젝트는 파일이 작아 파일
전체를 주고 길이 상한은 도구 층(clip)에 맡긴다 — 요약 생성은 2단계 과제.
층: adapters/java.
"""

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import extract_methods, find_class_file, parse_target


class JavaSourceInspector:
    """MavenProject 안에서 대상 식별자("Class" 또는 "Class#method")를 조사한다."""

    def __init__(self, project: MavenProject) -> None:
        self._project = project

    def inspect(self, target: str) -> str:
        class_name, method_name = parse_target(target)
        path = find_class_file(self._project, class_name)
        if path is None:
            return f"대상 없음: {target!r} — 클래스 {class_name!r} 파일을 찾지 못했다"
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(self._project.root)
        if method_name:
            methods = [m for m in extract_methods(source) if m.name == method_name]
            if not methods:
                names = [m.name for m in extract_methods(source)]
                return f"메서드 없음: {target!r}. {class_name}의 메서드: {names}"
            # 메서드만 주면 모델이 필드·import를 몰라 헤매므로 파일 전체를 함께 준다
            return f"파일: {rel}\n대상 메서드 {method_name} 발견 (파일 전체):\n{source}"
        return f"파일: {rel}\n{source}"
