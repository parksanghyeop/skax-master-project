"""변경 추출 — git diff를 "바뀐 클래스·메서드 목록"으로 바꾼다 (M5, v4 2.1 Step 1).

일반 코드다: 같은 diff를 넣으면 언제나 같은 목록이 나온다. git 실행은 대상
코드 실행이 아니므로 샌드박스 밖에서 해도 된다(R6은 코드 '실행' 금지).
층: adapters/java — diff의 줄 번호를 메서드로 매핑하는 데 언어 파싱이 필요하다.
"""

import re
import subprocess
from dataclasses import dataclass, field

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import _METHOD_SIGNATURE, method_line_spans
from cta.core.pipeline.models import ChangedSymbol

# 심볼당 diff 발췌 상한 — 분류 프롬프트 재료라 길 필요가 없다.
EXCERPT_MAX_CHARS = 1500

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<new_start>\d+)(?:,(?P<new_len>\d+))? @@")
_FILE_HEADER = re.compile(r"^\+\+\+ b/(?P<path>.+)$")


@dataclass
class _Bucket:
    added: int = 0
    removed: int = 0
    signature_changed: bool = False
    excerpts: list = field(default_factory=list)


class GitChangeExtractor:
    """git diff에서 변경 심볼을 뽑는다 (ChangeExtractor 포트 구현).

    입력: project — 대상 프로젝트(git 저장소여야 한다), base — 비교 기준
      (기본 HEAD: 아직 커밋하지 않은 변경을 본다. "HEAD~1" 등으로 커밋 범위도 가능).
    출력: 심볼("Class#method")별로 합산된 ChangedSymbol 목록. 메서드 밖 변경
      (import·필드)은 클래스 이름만으로 잡는다. 변경 없음 → 빈 목록.
    실패 시 동작: git 저장소가 아니면 RuntimeError(안내 포함).
    """

    def __init__(self, project: MavenProject, base: str = "HEAD") -> None:
        self._project = project
        self._base = base

    def extract(self) -> list[ChangedSymbol]:
        diff = self._run_git_diff()
        buckets: dict[str, _Bucket] = {}

        current_class = None
        current_spans = []
        new_line = 0  # 새 파일 기준 현재 줄 번호
        for line in diff.splitlines():
            file_match = _FILE_HEADER.match(line)
            if file_match:
                current_class, current_spans = self._load_file(file_match.group("path"))
                continue
            hunk = _HUNK_HEADER.match(line)
            if hunk:
                new_line = int(hunk.group("new_start"))
                continue
            if current_class is None:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                self._record(buckets, current_class, current_spans, new_line, line, added=True)
                new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                # 삭제 줄은 새 파일에 없다 — 삭제 지점(현재 new_line 위치)의 메서드로 귀속
                self._record(buckets, current_class, current_spans, new_line, line, added=False)
            elif not line.startswith("\\"):  # "\ No newline ..." 제외
                new_line += 1

        return [
            ChangedSymbol(
                target=target,
                lines_added=b.added,
                lines_removed=b.removed,
                signature_changed=b.signature_changed,
                diff_excerpt="\n".join(b.excerpts)[:EXCERPT_MAX_CHARS],
            )
            for target, b in sorted(buckets.items())
        ]

    def _run_git_diff(self) -> str:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self._project.root),
                "diff",
                # --relative: 프로젝트가 더 큰 git 저장소의 하위 폴더여도 경로가
                # 프로젝트 루트 기준으로 나온다 — 파일 매핑이 어긋나지 않게 하는 핵심
                "--relative",
                "--unified=0",
                self._base,
                "--",
                "*.java",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git diff 실패 — 대상이 git 저장소인지 확인하라: {result.stderr.strip()[:300]}"
            )
        return result.stdout

    def _load_file(self, rel_path: str):
        """변경 파일의 클래스 이름과 현재(새 버전) 메서드 줄 범위를 읽는다."""
        path = self._project.root / rel_path
        class_name = path.stem
        if not path.is_file():  # 파일 삭제 — 클래스 단위로만 잡는다
            return class_name, []
        return class_name, method_line_spans(path.read_text(encoding="utf-8", errors="replace"))

    def _record(self, buckets, class_name, spans, line_no, diff_line, added: bool) -> None:
        method = next((s.name for s in spans if s.start_line <= line_no <= s.end_line), None)
        target = f"{class_name}#{method}" if method else class_name
        bucket = buckets.setdefault(target, _Bucket())
        if added:
            bucket.added += 1
        else:
            bucket.removed += 1
        if _METHOD_SIGNATURE.search(diff_line[1:].strip() + " {"):
            # 변경 줄 자체가 메서드 선언 모양이면 시그니처가 손댄 것으로 본다(단서용 추정)
            bucket.signature_changed = True
        bucket.excerpts.append(diff_line)
