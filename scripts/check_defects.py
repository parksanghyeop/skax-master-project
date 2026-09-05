"""결함 세트 자기 검사 — 버그 버전이 컴파일되고 고친 버전과 관찰 가능하게 다른지 로컬 JDK로 확인.

왜 필요한가: 결함이 "동치 변이"(코드는 다르지만 동작이 같음)면 어떤 테스트도 잡을 수 없어
검출률을 깎는다. v1의 truncate-boundary가 그랬다(길이==max에서 `<`와 `<=`의 결과가 같음) —
e2e-notes 2주차 참조. case.toml의 probe(자바 식)를 고친 버전과 버그 버전에서 각각 평가해,
고친 쪽은 expected와 같고 버그 쪽은 다르면 통과.

Docker가 아니라 로컬 javac/java를 쓴다 — 대상 코드 실행이 아니라 결함 세트 정합성 검사이고
(R6의 취지 밖), 평가 하네스 실행(cta eval)은 여전히 샌드박스에서 돈다. CI(check 잡)에서도 돈다.

사용: python scripts/check_defects.py            # 전부
      python scripts/check_defects.py fib-base   # 일부
종료 코드: 0 전부 통과 / 1 실패 있음
"""

import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_SRC = (
    REPO_ROOT / "examples" / "evalbench" / "src" / "main" / "java" / "com" / "example" / "bench"
)
DEFECTS_DIR = REPO_ROOT / "cta" / "evals" / "defects"
PACKAGE = "com.example.bench"

# probe를 실행해 문자열 하나를 찍는 최소 진입점. 예외는 "throws <이름>"으로 통일해 비교한다
CHECK_JAVA = """package com.example.bench;
public class Check {
    public static void main(String[] args) {
        try {
            System.out.print(String.valueOf(%s));
        } catch (Throwable t) {
            System.out.print("throws " + t.getClass().getSimpleName());
        }
    }
}
"""


def _evaluate(sources: dict[str, str], probe: str) -> str:
    """sources(파일명→내용)와 probe로 임시 폴더에서 컴파일·실행해 출력 문자열을 돌려준다."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        out_dir = Path(tmp) / "out"
        src_dir.mkdir()
        for name, text in sources.items():
            (src_dir / name).write_text(text, encoding="utf-8")
        (src_dir / "Check.java").write_text(CHECK_JAVA % probe, encoding="utf-8")
        compile_ = subprocess.run(
            ["javac", "-encoding", "UTF-8", "-d", str(out_dir), *map(str, src_dir.glob("*.java"))],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if compile_.returncode != 0:
            return f"compile error: {compile_.stderr.strip()[:300]}"
        run = subprocess.run(
            ["java", "-cp", str(out_dir), f"{PACKAGE}.Check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return run.stdout if run.returncode == 0 else f"runtime error: {run.stderr.strip()[:300]}"


def check_case(case_dir: Path) -> tuple[bool, str]:
    """케이스 하나. (통과 여부, 한 줄 설명)."""
    meta = tomllib.loads((case_dir / "case.toml").read_text(encoding="utf-8"))
    probe, expected = meta.get("probe"), meta.get("expected")
    if probe is None or expected is None:
        return False, "case.toml에 probe/expected가 없다"
    fixed = {p.name: p.read_text(encoding="utf-8") for p in BENCH_SRC.glob("*.java")}
    buggy_name = Path(meta["class_rel"]).name
    if fixed[buggy_name] == (case_dir / "Buggy.java").read_text(encoding="utf-8"):
        return False, "Buggy.java가 고친 버전과 같다"
    buggy = dict(fixed)
    buggy[buggy_name] = (case_dir / "Buggy.java").read_text(encoding="utf-8")
    fixed_out = _evaluate(fixed, probe)
    buggy_out = _evaluate(buggy, probe)
    if fixed_out != expected:
        return False, f"고친 버전이 expected와 다르다: {fixed_out!r} != {expected!r}"
    if buggy_out == expected:
        return False, f"동치 변이 — 버그 버전도 {buggy_out!r} (관찰 불가, 어떤 테스트도 못 잡는다)"
    return True, f"고친 {fixed_out!r} / 버그 {buggy_out!r}"


def main(argv: list[str]) -> int:
    if shutil.which("javac") is None or shutil.which("java") is None:
        print("javac/java가 PATH에 없다 — JDK 17+ 필요")
        return 1
    wanted = set(argv)
    dirs = sorted(d for d in DEFECTS_DIR.iterdir() if (d / "case.toml").is_file())
    if wanted:
        dirs = [d for d in dirs if d.name in wanted]
    failures = 0
    for d in dirs:
        ok, note = check_case(d)
        failures += 0 if ok else 1
        print(f"{'통과' if ok else '실패'}  {d.name:<26} {note}")
    print(f"\n{len(dirs) - failures}/{len(dirs)} 통과")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
