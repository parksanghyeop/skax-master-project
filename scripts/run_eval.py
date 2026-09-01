"""평가 하네스 (M7) — 결함 세트로 검출률 등 지표를 실측해 evals/results/에 기록한다.

원리(테스트 스트리핑의 변형): 각 케이스는 (고친 버전, 버그 버전) 쌍이다.
  1) 고친 버전에서 에이전트가 테스트를 생성한다 (게이트 포함, 사람 개입 없음)
  2) 생성 테스트를 버그 버전에 돌린다 — **실패하면 버그를 잡은 것(검출 성공)**
  3) 원상 복구
지표: 검출률, 게이트 통과율, 에스컬레이션율, 시도 수(≈LLM 호출 수), 소요 시간.
수치는 모델·프롬프트 해시·데이터셋 버전에 묶여 기록된다(고도화 규칙: 재현 가능).

사용: .venv/Scripts/python scripts/run_eval.py [--fast] [--cases id1,id2]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 리포 루트를 import 경로에

from adapters.java.maven import detect_maven_project  # noqa: E402
from adapters.java.runner import JavaTestRunner  # noqa: E402
from sandbox.docker_sandbox import DockerSandbox  # noqa: E402
from scripts.generate_test import run_generation  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH = REPO_ROOT / "examples" / "evalbench"
DEFECTS_DIR = REPO_ROOT / "evals" / "defects"
RESULTS_DIR = REPO_ROOT / "evals" / "results"
DATASET_VERSION = "local-defects-v1"  # 케이스를 추가·수정하면 반드시 올린다


def prompt_hash() -> str:
    """프롬프트 파일 전체의 해시 — 수치가 어떤 지시문에서 나왔는지 묶는 열쇠."""
    h = hashlib.sha256()
    for p in sorted((REPO_ROOT / "llm" / "prompts").glob("*.md")):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def reset_bench() -> None:
    """벤치 프로젝트를 커밋 상태로 되돌리고 생성물·빌드 산출물을 지운다."""
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "checkout", "--", "examples/evalbench"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "clean", "-fdq", "--", "examples/evalbench"],
        check=True,
        capture_output=True,
    )
    shutil.rmtree(BENCH / "target", ignore_errors=True)


def run_case(case_dir: Path, fast: bool) -> dict:
    """케이스 하나: 생성(고친 버전) → 버그 버전에서 검출 확인 → 복구."""
    meta = tomllib.loads((case_dir / "case.toml").read_text(encoding="utf-8"))
    target = meta["target"]
    class_rel = meta["class_rel"]
    row = {"case": case_dir.name, "target": target, "bug": meta["bug"]}
    print(f"\n=== 케이스 {case_dir.name} ({target}) ===")
    reset_bench()
    try:
        outcome = run_generation(
            project_path=str(BENCH),
            target=target,
            fast=fast,
            ask_user=None,  # 하네스는 무인 실행 — 멈춤 지점은 자동 '계속'
        )
        row.update(
            status=outcome["status"],
            gate_attempts=outcome.get("attempts", 0),
            writer_attempts=outcome.get("writer_attempts", 0),
            elapsed=round(outcome.get("elapsed", 0.0), 1),
            gates={n: p for n, p, _ in outcome.get("gate_results", [])},
        )
        if outcome["status"] != "accepted":
            row["detected"] = None  # 생성 자체가 승인되지 않음 — 검출 판정 불가
            print(f"생성 미승인: {outcome['status']}")
            return row

        # 버그 버전을 심고, 생성된 테스트만 실행한다 — 실패해야 검출 성공
        test_class = Path(outcome["test_path"]).stem
        (BENCH / class_rel).write_text(
            (case_dir / "Buggy.java").read_text(encoding="utf-8"), encoding="utf-8"
        )
        project = detect_maven_project(BENCH)
        runner = JavaTestRunner(project, DockerSandbox(), BENCH / ".cta" / "m2repo")
        result = runner.run(test_class)
        row["detected"] = not result.passed
        print(
            f"검출: {'성공(버그에서 테스트 실패)' if row['detected'] else '실패(버그를 통과시킴)'}"
        )
        return row
    finally:
        reset_bench()


def main() -> int:
    parser = argparse.ArgumentParser(description="결함 세트 평가 하네스")
    parser.add_argument("--fast", action="store_true", help="커버리지·뮤테이션 게이트 생략")
    parser.add_argument("--cases", help="쉼표로 구분한 케이스 id 필터 (기본: 전체)")
    args = parser.parse_args()

    case_dirs = sorted(d for d in DEFECTS_DIR.iterdir() if (d / "case.toml").is_file())
    if args.cases:
        wanted = set(args.cases.split(","))
        case_dirs = [d for d in case_dirs if d.name in wanted]
    if not case_dirs:
        print("케이스 없음")
        return 1

    started = time.monotonic()
    rows = [run_case(d, args.fast) for d in case_dirs]
    total_elapsed = time.monotonic() - started

    accepted = [r for r in rows if r.get("status") == "accepted"]
    detected = [r for r in accepted if r.get("detected")]
    escalated = [r for r in rows if r.get("status") in ("human_review", "not_passed")]
    summary = {
        "cases": len(rows),
        "accepted": len(accepted),
        "detected": len(detected),
        "detection_rate": round(len(detected) / len(rows), 3),
        "escalation_rate": round(len(escalated) / len(rows), 3),
        "avg_writer_attempts": round(sum(r.get("writer_attempts", 0) for r in rows) / len(rows), 2),
        "total_elapsed_s": round(total_elapsed, 1),
    }
    record = {
        "dataset": DATASET_VERSION,
        "model": None,  # 아래에서 설정에서 읽어 채운다 (전 케이스 동일 모델)
        "prompt_hash": prompt_hash(),
        "gates": "fast(3종)" if args.fast else "full(5종)",
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "rows": rows,
    }
    # 모델 이름은 케이스 실행 결과에서 (전 케이스 동일)
    from llm.config import make_llm_client

    record["model"] = make_llm_client()[1]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"eval-{DATASET_VERSION}-{record['model']}-{stamp}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 평가 요약 =====")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"기록: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
