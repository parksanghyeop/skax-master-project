"""cta eval — 결함 세트로 검출률 등 지표를 실측해 evals/results/에 기록한다 (M7).

원리(테스트 스트리핑의 변형): 각 케이스는 (고친 버전, 버그 버전) 쌍이다.
  1) 고친 버전에서 테스트를 생성한다 (게이트 포함, 사람 개입 없음) → 제안 반영
  2) 생성 테스트를 버그 버전에 돌린다 — 실패하면 버그를 잡은 것(검출 성공)
  3) 원상 복구
수치는 모델·프롬프트 해시·데이터셋 버전에 묶여 기록된다(재현 가능성).
"""

import hashlib
import json
import shutil
import subprocess
import time
import tomllib
from datetime import datetime
from pathlib import Path

from cta.adapters.java.maven import detect_maven_project
from cta.adapters.java.runner import JavaTestRunner
from cta.cli.generate import run_generation
from cta.cli.proposals import apply_proposal
from cta.sandbox.docker_sandbox import DockerSandbox

REPO_ROOT = Path(__file__).resolve().parents[2]  # cta/cli/ → 리포 루트
BENCH = REPO_ROOT / "examples" / "evalbench"
DEFECTS_DIR = REPO_ROOT / "cta" / "evals" / "defects"
RESULTS_DIR = REPO_ROOT / "cta" / "evals" / "results"
DATASET_VERSION = "local-defects-v1"  # 케이스를 추가·수정하면 반드시 올린다


def prompt_hash() -> str:
    """프롬프트 파일 전체의 해시 — 수치가 어떤 지시문에서 나왔는지 묶는 열쇠."""
    h = hashlib.sha256()
    for p in sorted((REPO_ROOT / "cta" / "llm" / "prompts").glob("*.md")):
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
    """케이스 하나: 생성(고친 버전)→제안 반영 → 버그 버전에서 검출 확인 → 복구."""
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

        # 제안을 반영한 뒤 버그 버전을 심고, 생성된 테스트만 실행 — 실패해야 검출 성공
        project = detect_maven_project(BENCH)
        apply_proposal(project, outcome["proposal"])
        (BENCH / class_rel).write_text(
            (case_dir / "Buggy.java").read_text(encoding="utf-8"), encoding="utf-8"
        )
        runner = JavaTestRunner(project, DockerSandbox(), BENCH / ".cta" / "m2repo")
        result = runner.run(outcome["proposal"])
        row["detected"] = not result.passed
        print(
            f"검출: {'성공(버그에서 테스트 실패)' if row['detected'] else '실패(버그를 통과시킴)'}"
        )
        return row
    finally:
        reset_bench()


def run_eval(args) -> int:
    # 개발 리포 전용 — 결함 세트·벤치 프로젝트가 리포에 있어야 돈다
    if not DEFECTS_DIR.is_dir() or not BENCH.is_dir():
        print("cta eval은 개발 리포지토리 안에서만 동작한다 (결함 세트·벤치 필요).")
        return 1
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
    from cta.llm.config import make_llm_client

    record = {
        "dataset": DATASET_VERSION,
        "model": make_llm_client()[1],
        "prompt_hash": prompt_hash(),
        "gates": "fast(3종)" if args.fast else "full(5종)",
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "rows": rows,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"eval-{DATASET_VERSION}-{record['model']}-{stamp}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 평가 요약 =====")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"기록: {out}")
    return 0
