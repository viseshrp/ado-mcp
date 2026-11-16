from datetime import date
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- Fixed commands and isolated fixture paths only.
        args, cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8"
    )


@pytest.fixture
def release_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    git = shutil.which("git")
    bash = (
        str(Path(git).parents[1] / "bin" / "bash.exe")
        if git and os.name == "nt"
        else shutil.which("bash")
    )
    if not git or not bash or not Path(bash).is_file():
        pytest.skip("Release helper tests require Git and Bash.")

    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    repo.mkdir()
    run([git, "init", "--bare", str(remote)], tmp_path)
    run([git, "init", "-b", "main", str(repo)], tmp_path)
    for key, value in (("user.name", "Release Test"), ("user.email", "test@example.com")):
        run([git, "config", key, value], repo)
    (repo / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts" / "check_changelog_date.py", repo / "scripts")
    (repo / "CHANGELOG.md").write_text(
        f"## [0.0.1] - {date.today()}\n\n## [0.1.0] - {date.today()}\n",
        encoding="utf-8",
    )
    for args in (
        ["add", "."],
        ["commit", "-m", "Release fixture"],
        ["remote", "add", "origin", str(remote)],
        ["push", "-u", "origin", "main"],
    ):
        run([git, *args], repo)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$*" == "run hatch version" ]]; then\n'
        '  echo "0.0.1.dev20000101000000"\n'
        'elif [[ "$1" == run && "$2" == python ]]; then\n'
        "  shift 2\n"
        f'  exec {shlex.quote(sys.executable)} "$@"\n'
        "else\n"
        "  exit 2\n"
        "fi\n",
        encoding="utf-8",
        newline="\n",
    )
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    return repo, bash


@pytest.mark.parametrize(("args", "version"), [([], "0.0.1"), (["0.1.0"], "0.1.0")])
def test_release_helper_pushes_selected_version(
    release_repo: tuple[Path, str], args: list[str], version: str
) -> None:
    repo, bash = release_repo
    result = run(
        [bash, str(ROOT / "scripts" / "tag_release.sh"), *args],
        repo,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    remote_tags = run(["git", "ls-remote", "--tags", "origin"], repo)
    assert f"refs/tags/v{version}^{{}}" in remote_tags.stdout


@pytest.mark.parametrize("version", ["not-a-version", "01.2.3", "0.0.0"])
def test_release_helper_rejects_invalid_or_older_version(
    release_repo: tuple[Path, str], version: str
) -> None:
    repo, bash = release_repo
    result = run(
        [bash, str(ROOT / "scripts" / "tag_release.sh"), version],
        repo,
        check=False,
    )

    assert result.returncode != 0
    assert "Release version" in result.stderr
    tags = run(["git", "tag"], repo)
    assert not tags.stdout
