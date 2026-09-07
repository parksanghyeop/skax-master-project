"""cta eval --intents — 의도 세트로 의도 분류의 정확도·unclear 비율을 실측한다 (ADR-0020 D4).

원리: 케이스마다 예제 프로젝트(examples/demo)를 임시 폴더에 복사해 독립 git 저장소로 만들고,
"변경 전 → 변경 후" 치환을 적용한 뒤 실제 변경 추출기 + 의도 분류기(LLM)를 돌린다.
같은 케이스를 **커밋 메시지 있음 / 없음(미커밋)** 두 변형으로 실행해, 메시지가 없을 때
unclear로 얼마나 빠지는지 따로 본다. Docker·테스트 실행은 없다(분류만 본다).
수치는 모델·프롬프트 해시·데이터셋 버전과 묶어 기록한다. 층: cli(개발용 명령).
"""

import argparse
import json
import shutil
import subprocess
import tempfile
import time
import tomllib
from datetime import datetime
from pathlib import Path

from cta.adapters.java.changes import GitChangeExtractor
from cta.adapters.java.maven import detect_maven_project
from cta.cli.eval_cmd import prompt_hash
from cta.core.pipeline.maintain import analyze_changes
from cta.llm.config import load_dotenv_into_env, make_llm_client
from cta.llm.intent import PromptedIntentClassifier
from cta.llm.metering import MeteredClient

REPO_ROOT = Path(__file__).resolve().parents[2]  # cta/cli/ → 리포 루트
DEMO = REPO_ROOT / "examples" / "demo"
INTENTS_DIR = REPO_ROOT / "cta" / "evals" / "intents"
RESULTS_DIR = REPO_ROOT / "cta" / "evals" / "results"
DATASET_VERSION = "local-intents-v1"  # 케이스를 추가·수정하면 반드시 올린다

# 복사에서 빼는 것 — 의존성 캐시(161MB)·빌드 산출물·시크릿은 분류에 필요 없다
_SKIP_DIRS = {".cta", "target", ".git", "__pycache__"}
_SKIP_FILES = {".env", "pom-cta-pit.xml"}


class _NoTests:
    """검증 테스트 찾기·실행을 비활성화하는 대본 — 이 하네스는 분류만 본다."""

    def find(self, target: str) -> list[str]:
        return []

    def run(self, selector: str):
        raise AssertionError("의도 세트 하네스는 테스트를 실행하지 않는다")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=eval@example.com", "-c", "user.name=eval"]
        + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} 실패: {result.stderr[:300]}")
    return result.stdout


def _copy_demo(out: Path) -> None:
    def ignored(_dir, names):
        return [n for n in names if n in _SKIP_DIRS or n in _SKIP_FILES]

    shutil.copytree(DEMO, out, ignore=ignored)


def prepare_repo(case: dict, out: Path, with_message: bool) -> str:
    """예제 복사 → 기준선 커밋 → 변경 적용(→ 메시지 변형이면 커밋). 반환: 비교 기준(base)."""
    _copy_demo(out)
    source = out / case["file"]
    text = source.read_text(encoding="utf-8")
    before, after = case["before"], case["after"]
    # 예제 원본이 '변경 후' 상태인 케이스(버그 수정)는 되돌려서 기준선을 만든다
    if before not in text:
        if after not in text:
            raise RuntimeError(f"{case['file']}에서 before/after 어느 쪽도 찾지 못했다")
        text = text.replace(after, before, 1)
        source.write_text(text, encoding="utf-8")
    _git(out, "init", "-q")
    _git(out, "add", "-A")
    _git(out, "commit", "-qm", "chore: 기준선")
    source.write_text(text.replace(before, after, 1), encoding="utf-8")
    if with_message:
        _git(out, "commit", "-qam", case["message"])
        return "HEAD~1"
    return "HEAD"


def run_case(case_dir: Path, with_message: bool, classifier, client: MeteredClient) -> dict:
    """케이스 하나·변형 하나를 분류하고 정답과 비교한 행을 돌려준다."""
    case = tomllib.loads((case_dir / "case.toml").read_text(encoding="utf-8"))
    row = {
        "case": case_dir.name,
        "variant": "with_message" if with_message else "no_message",
        "target": case["target"],
        "expected": case["expected"],
    }
    tmp = Path(tempfile.mkdtemp(prefix="cta-int-"))
    tokens_before = client.total_tokens
    started = time.monotonic()
    try:
        repo = tmp / "repo"  # copytree는 없는 폴더를 원한다
        base = prepare_repo(case, repo, with_message)
        project = detect_maven_project(str(repo))
        change_set = GitChangeExtractor(project, base).extract()
        analyses = analyze_changes(change_set, classifier, _NoTests(), _NoTests())
        hit = next((a for a in analyses if a.change.target == case["target"]), None)
        if hit is None:
            row.update(
                actual="(추출 안 됨)",
                correct=False,
                extracted=[a.change.target for a in analyses],
            )
        else:
            row.update(
                actual=hit.intent.category,
                confidence=round(hit.intent.confidence, 2),
                evidence=list(hit.intent.evidence),
                correct=hit.intent.category == case["expected"],
            )
    except Exception as e:  # 케이스 하나의 실패가 전체 측정을 멈추지 않게
        row.update(actual="(오류)", correct=False, error=str(e)[:300])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    row["elapsed"] = round(time.monotonic() - started, 1)
    row["tokens"] = client.total_tokens - tokens_before
    return row


def _summarize(rows: list[dict]) -> dict:
    def stats(subset: list[dict]) -> dict:
        n = len(subset)
        if n == 0:
            return {"runs": 0}
        unclear = [r for r in subset if r.get("actual") == "unclear"]
        return {
            "runs": n,
            "accuracy": round(sum(1 for r in subset if r["correct"]) / n, 3),
            "unclear_rate": round(len(unclear) / n, 3),
            "avg_elapsed_s": round(sum(r["elapsed"] for r in subset) / n, 1),
        }

    return {
        "all": stats(rows),
        "with_message": stats([r for r in rows if r["variant"] == "with_message"]),
        "no_message": stats([r for r in rows if r["variant"] == "no_message"]),
        # 정답이 unclear가 아닌데 unclear로 나온 것 — 사용자가 겪는 "의도 모름" 그 자체
        "false_unclear": sum(
            1 for r in rows if r.get("actual") == "unclear" and r["expected"] != "unclear"
        ),
        "total_tokens": sum(r["tokens"] for r in rows),
    }


def run_eval_intents(args: argparse.Namespace) -> int:
    load_dotenv_into_env()
    raw_client, model = make_llm_client()
    client = MeteredClient(raw_client)
    classifier = PromptedIntentClassifier(client, model)

    case_dirs = sorted(p for p in INTENTS_DIR.iterdir() if (p / "case.toml").is_file())
    if getattr(args, "cases", None):
        wanted = set(args.cases.split(","))
        case_dirs = [p for p in case_dirs if p.name in wanted]
    variants = [True, False]
    if getattr(args, "variant", "both") == "with":
        variants = [True]
    elif getattr(args, "variant", "both") == "without":
        variants = [False]

    rows = []
    for case_dir in case_dirs:
        for with_message in variants:
            row = run_case(case_dir, with_message, classifier, client)
            rows.append(row)
            mark = "O" if row["correct"] else "X"
            conf = f" ({row['confidence']:.0%})" if "confidence" in row else ""
            print(
                f"  [{mark}] {row['case']:28} {row['variant']:12} "
                f"기대 {row['expected']:11} → {row['actual']}{conf}  {row['elapsed']}초",
                flush=True,
            )

    summary = _summarize(rows)
    record = {
        "dataset": DATASET_VERSION,
        "model": model,
        "prompt_hash": prompt_hash(),
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "rows": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"intents-{DATASET_VERSION}-{model}-{stamp}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 의도 세트 요약 =====")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"기록: {out}")
    return 0
