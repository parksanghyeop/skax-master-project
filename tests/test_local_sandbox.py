"""로컬 실행 샌드박스(ADR-0019) — 경로 번역·플래그 제거·실행 장치 선택·mvn 없음 안내."""

import subprocess

import pytest

import cta.sandbox.local_sandbox as local_module
from cta.cli.hints import render_error
from cta.sandbox.docker_sandbox import DockerSandbox, Mount, SandboxResult
from cta.sandbox.factory import (
    RUNNER_DOCKER,
    RUNNER_LOCAL,
    choose_runner,
    make_sandbox,
)
from cta.sandbox.local_sandbox import LocalSandbox, strip_sandbox_only_flags, translate_paths

MOUNTS = [Mount("C:/proj", "/work"), Mount("C:/proj/.cta/m2repo", "/m2repo", read_only=True)]


class TestTranslation:
    def test_컨테이너_경로를_호스트_경로로_경계에서만_바꾼다(self):
        args = ["/work", "/work/pom.xml", "/workspace/x", "-Dtest=Foo"]
        assert translate_paths(args, MOUNTS) == [
            "C:/proj",
            "C:/proj/pom.xml",
            "/workspace/x",  # '/work'로 시작하지만 경계가 아니다 — 건드리지 않는다
            "-Dtest=Foo",
        ]

    def test_오프라인과_캐시_경로_인자를_뺀다(self):
        args = ["mvn", "-B", "-o", "-Dmaven.repo.local=/m2repo", "test", "-Dtest=FooTest"]
        assert strip_sandbox_only_flags(args) == ["mvn", "-B", "test", "-Dtest=FooTest"]


class TestChooseRunner:
    def test_기본은_docker이고_fast면_local이다(self):
        assert choose_runner(None, fast=False) == RUNNER_DOCKER
        assert choose_runner(None, fast=True) == RUNNER_LOCAL

    def test_명시한_runner가_fast보다_이긴다(self):
        assert choose_runner("docker", fast=True) == RUNNER_DOCKER  # CI: 격리 유지 + 게이트만 생략

    def test_모르는_이름은_거부한다(self):
        with pytest.raises(ValueError):
            choose_runner("podman", fast=False)

    def test_이름으로_실행_장치를_만든다(self):
        assert isinstance(make_sandbox(RUNNER_LOCAL), LocalSandbox)
        assert isinstance(make_sandbox(RUNNER_DOCKER), DockerSandbox)


class TestLocalRun:
    def test_호스트_mvn을_프로젝트_폴더에서_실행하고_샌드박스_인자는_뺀다(self, monkeypatch):
        seen: dict = {}

        def fake_run(argv, **kwargs):
            seen["argv"], seen["cwd"] = argv, kwargs["cwd"]
            return subprocess.CompletedProcess(argv, 0, stdout="Tests run: 1", stderr="")

        monkeypatch.setattr(local_module.shutil, "which", lambda name: f"C:/tools/{name}.cmd")
        monkeypatch.setattr(local_module.subprocess, "run", fake_run)
        result = LocalSandbox().run(
            image="maven:3.9-eclipse-temurin-21",
            command=["mvn", "-B", "-o", "-Dmaven.repo.local=/m2repo", "test", "-Dtest=FooTest"],
            mounts=MOUNTS,
            workdir="/work",
            network_enabled=False,
        )
        assert result == SandboxResult(0, "Tests run: 1")
        assert seen["argv"] == ["C:/tools/mvn.cmd", "-B", "test", "-Dtest=FooTest"]
        assert seen["cwd"] == "C:/proj"

    def test_mvn이_없으면_mvn을_담은_FileNotFoundError이고_안내가_붙는다(self, monkeypatch):
        monkeypatch.setattr(local_module.shutil, "which", lambda name: None)
        with pytest.raises(FileNotFoundError, match="mvn") as info:
            LocalSandbox().run("img", ["mvn", "test"], MOUNTS, "/work")
        text = render_error(info.value)
        assert "--runner docker" in text and "mvn -version" in text
