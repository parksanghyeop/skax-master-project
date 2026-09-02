"""변경 추출 — git diff를 "바뀐 클래스·메서드 목록 + 판단 단서"로 바꾼다 (v4 2.1 Step 1).

일반 코드다: 같은 diff를 넣으면 언제나 같은 목록이 나온다. git 실행은 대상
코드 실행이 아니므로 샌드박스 밖에서 해도 된다(R6은 코드 '실행' 금지).
단서(시나리오 SC-002 2단계): 시그니처 변경, 접근 제어자 변경, 바뀐 줄 수, 커밋 메시지,
이슈 번호 — 전부 여기서 결정적으로 뽑아 의도 분류와 화면 출력에 넘긴다.
층: adapters/java — diff의 줄 번호를 메서드로 매핑하는 데 언어 파싱이 필요하다.
"""

import re
import subprocess
from dataclasses import dataclass, field

from cta.adapters.java.maven import MavenProject
from cta.adapters.java.parsing import _METHOD_SIGNATURE, access_modifier, method_line_spans
from cta.core.pipeline.models import ChangedSymbol, ChangeSet

# 심볼당 diff 발췌 상한 — 분류 프롬프트 재료라 길 필요가 없다.
EXCERPT_MAX_CHARS = 1500

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<new_start>\d+)(?:,(?P<new_len>\d+))? @@")
_FILE_HEADER = re.compile(r"^\+\+\+ b/(?P<path>.+)$")

# 이슈 참조 — "#4821", "ISSUE-12" 같은 흔한 표기
_ISSUE_REF = re.compile(r"(?:#\d+|\b[A-Z][A-Z0-9]+-\d+\b)")

# 주석 줄 판정 — 줄 전체가 // 또는 /* ... */ 블록의 일부인 경우만. 코드 뒤 주석은 코드로 본다
_COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*|\*/)")

# 수정 전 소스가 필요한 대상 — 재발 방지 검증(SC-002 7단계)은 main 소스만 바꿔 끼운다
_MAIN_PREFIX = "src/main/java/"


@dataclass
class _Bucket:
    added: int = 0
    removed: int = 0
    signature_changed: bool = False
    access_before: set = field(default_factory=set)
    access_after: set = field(default_factory=set)
    code_lines: int = 0  # 주석·공백이 아닌 변경 줄 수 — 0이면 의미 없는 변경
    file_rel: str = ""
    change_line: int = 0
    excerpts: list = field(default_factory=list)


class GitChangeExtractor:
    """git diff에서 변경 심볼과 단서를 뽑는다 (ChangeExtractor 포트 구현).

    입력: project — 대상 프로젝트(git 저장소여야 한다), base — 비교 기준
      (기본 HEAD: 아직 커밋하지 않은 변경을 본다. "HEAD~1" 등으로 커밋 범위도 가능).
    출력: ChangeSet — 심볼("Class#method")별로 합산된 ChangedSymbol 목록 + 커밋 메시지·
      이슈 번호. 메서드 밖 변경(import·필드)은 클래스 이름만으로 잡는다. 변경 없음 → 빈 목록.
    실패 시 동작: git 저장소가 아니면 RuntimeError(안내 포함).
    """

    def __init__(self, project: MavenProject, base: str = "HEAD") -> None:
        self._project = project
        self._base = base

    @property
    def base(self) -> str:
        return self._base

    def extract(self) -> ChangeSet:
        diff = self._run_git(["diff", "--relative", "--unified=0", self._base, "--", "*.java"])
        buckets: dict[str, _Bucket] = {}

        current_class = None
        current_rel = ""
        current_spans = []
        new_line = 0  # 새 파일 기준 현재 줄 번호
        for line in diff.splitlines():
            file_match = _FILE_HEADER.match(line)
            if file_match:
                current_rel = file_match.group("path")
                current_class, current_spans = self._load_file(current_rel)
                continue
            hunk = _HUNK_HEADER.match(line)
            if hunk:
                new_line = int(hunk.group("new_start"))
                continue
            if current_class is None:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                self._record(
                    buckets, current_class, current_rel, current_spans, new_line, line, added=True
                )
                new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                # 삭제 줄은 새 파일에 없다 — 삭제 지점(현재 new_line 위치)의 메서드로 귀속
                self._record(
                    buckets, current_class, current_rel, current_spans, new_line, line, added=False
                )
            elif not line.startswith("\\"):  # "\ No newline ..." 제외
                new_line += 1

        symbols = [
            ChangedSymbol(
                target=target,
                lines_added=b.added,
                lines_removed=b.removed,
                signature_changed=b.signature_changed,
                diff_excerpt="\n".join(b.excerpts)[:EXCERPT_MAX_CHARS],
                access_changed=bool(b.access_before or b.access_after)
                and b.access_before != b.access_after,
                comment_only=b.code_lines == 0,
                file_rel=b.file_rel,
                change_line=b.change_line,
            )
            for target, b in sorted(buckets.items())
        ]
        message = self.commit_message()
        return ChangeSet(
            symbols=symbols,
            commit_message=message,
            issue_refs=tuple(dict.fromkeys(_ISSUE_REF.findall(message))),
        )

    def commit_message(self) -> str:
        """비교 범위(base..HEAD)의 커밋 메시지들. 미커밋 변경(base=HEAD)이면 빈 문자열."""
        if self._base.strip() == "HEAD":
            return ""
        try:
            return self._run_git(["log", "--format=%B", f"{self._base}..HEAD"]).strip()
        except RuntimeError:
            return ""

    def old_source(self, file_rel: str) -> str | None:
        """base 시점의 파일 내용. base에 없던 파일(신규)이면 None.

        왜 필요한가: 재발 방지 테스트를 수정 전 코드에 적용해 실패하는지 확인한다(SC-002 7단계).
        `./`를 붙이는 이유: git show의 경로는 저장소 루트 기준이라, 하위 폴더 프로젝트에서
        프로젝트 기준 상대 경로를 쓰려면 현재 폴더 기준 표기가 필요하다.
        """
        result = subprocess.run(
            ["git", "-C", str(self._project.root), "show", f"{self._base}:./{file_rel}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout if result.returncode == 0 else None

    def old_main_sources(self, change_set: ChangeSet) -> dict[str, str | None]:
        """변경된 main 소스 파일마다 수정 전 내용을 모은다 (재발 방지 게이트 입력)."""
        files = sorted(
            {s.file_rel for s in change_set.symbols if s.file_rel.startswith(_MAIN_PREFIX)}
        )
        return {rel: self.old_source(rel) for rel in files}

    def _run_git(self, args: list[str]) -> str:
        # --relative: 프로젝트가 더 큰 git 저장소의 하위 폴더여도 경로가 프로젝트 루트 기준으로
        # 나온다 — 파일 매핑이 어긋나지 않게 하는 핵심 (diff 호출 시 인자로 포함)
        result = subprocess.run(
            ["git", "-C", str(self._project.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            detail = result.stderr.strip()[:300]
            raise RuntimeError(f"git {args[0]} 실패 — 대상이 git 저장소인지 확인하라: {detail}")
        return result.stdout

    def _load_file(self, rel_path: str):
        """변경 파일의 클래스 이름과 현재(새 버전) 메서드 줄 범위를 읽는다."""
        path = self._project.root / rel_path
        class_name = path.stem
        if not path.is_file():  # 파일 삭제 — 클래스 단위로만 잡는다
            return class_name, []
        return class_name, method_line_spans(path.read_text(encoding="utf-8", errors="replace"))

    def _record(self, buckets, class_name, rel, spans, line_no, diff_line, added: bool) -> None:
        method = next((s.name for s in spans if s.start_line <= line_no <= s.end_line), None)
        target = f"{class_name}#{method}" if method else class_name
        bucket = buckets.setdefault(target, _Bucket())
        if not bucket.file_rel:
            bucket.file_rel = rel
            bucket.change_line = line_no
        if added:
            bucket.added += 1
        else:
            bucket.removed += 1
        body = diff_line[1:]
        if body.strip() and not _COMMENT_LINE.match(body):
            bucket.code_lines += 1
        if _METHOD_SIGNATURE.search(body.strip() + " {"):
            # 변경 줄 자체가 메서드 선언 모양이면 시그니처가 손댄 것으로 본다(단서용 추정)
            bucket.signature_changed = True
            (bucket.access_after if added else bucket.access_before).add(access_modifier(body))
        bucket.excerpts.append(diff_line)


class ReferencingTestLocator:
    """기존 테스트 소스에서 대상을 참조하는 테스트 클래스를 찾는다 (TestLocator 폴백 구현).

    그래프(COVERS 실측)가 없을 때의 결정적 근사: 테스트 파일 안에 클래스 이름과
    "메서드이름(" 호출 모양이 함께 있으면 그 테스트가 대상을 검증한다고 본다.
    """

    def __init__(self, project: MavenProject) -> None:
        self._project = project

    def find(self, target: str) -> list[str]:
        class_name, _, method_name = target.partition("#")
        test_dir = self._project.test_source_dir
        if not test_dir.is_dir():
            return []
        call = re.compile(rf"\b{re.escape(method_name)}\s*\(") if method_name else None
        hits = []
        for path in sorted(test_dir.rglob("*.java")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if class_name not in text:
                continue
            if call is None or call.search(text):
                hits.append(path.stem)
        return hits
