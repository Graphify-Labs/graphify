"""Tests for the GitLab change-request provider."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from graphify import gitlab
from graphify.prs import fetch_pr_files, fetch_prs


class TestGitLabConfig:
    def test_parse_https_remote(self):
        assert gitlab._parse_remote(
            "https://gitlab.example.com/group/sub/project.git"
        ) == ("https://gitlab.example.com", "group/sub/project")

    def test_parse_ssh_remote(self):
        assert gitlab._parse_remote(
            "git@gitlab.example.com:group/sub/project.git"
        ) == ("https://gitlab.example.com", "group/sub/project")

    def test_resolve_from_origin_and_environment_token(self):
        with patch.dict(
            "os.environ",
            {"GITLAB_TOKEN": "secret"},
            clear=True,
        ), patch(
            "graphify.gitlab._origin_url",
            return_value="https://gitlab.example.com/group/project.git",
        ):
            config = gitlab.resolve_config()
        assert config.base_url == "https://gitlab.example.com"
        assert config.project == "group/project"
        assert config.token == "secret"

    def test_explicit_project_uses_configured_url(self):
        with patch.dict(
            "os.environ",
            {"GITLAB_URL": "https://gitlab.example.com"},
            clear=True,
        ):
            config = gitlab.resolve_config("group/project")
        assert config.project == "group/project"

    def test_complete_environment_skips_origin_lookup(self):
        environment = {
            "GITLAB_URL": "https://gitlab.example.com",
            "GITLAB_PROJECT": "group/project",
        }
        with patch.dict("os.environ", environment, clear=True), patch(
            "graphify.gitlab._origin_url"
        ) as origin:
            config = gitlab.resolve_config()
        assert config.project == "group/project"
        origin.assert_not_called()

    def test_opt_in_uses_git_credential_manager(self):
        environment = {
            "GITLAB_URL": "https://gitlab.example.com",
            "GRAPHIFY_GITLAB_USE_GIT_CREDENTIALS": "true",
        }
        with patch.dict("os.environ", environment, clear=True), patch(
            "graphify.gitlab._git_credential_token", return_value="credential-token"
        ):
            config = gitlab.resolve_config("group/project")
        assert config.token == "credential-token"

    def test_git_credential_parser_returns_password(self):
        gitlab._git_credential_token.cache_clear()
        result = type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "protocol=https\nhost=gitlab.example.com\npassword=token\n",
            },
        )()
        with patch("graphify.gitlab.subprocess.run", return_value=result) as run:
            assert gitlab._git_credential_token(
                "https://gitlab.example.com"
            ) == "token"
            assert gitlab._git_credential_token(
                "https://gitlab.example.com"
            ) == "token"
        assert run.call_count == 1
        assert run.call_args.kwargs["env"]["GCM_INTERACTIVE"] == "Never"
        assert run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


class TestPipelineStatus:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("success", "SUCCESS"),
            ("failed", "FAILURE"),
            ("canceled", "FAILURE"),
            ("running", "PENDING"),
            ("pending", "PENDING"),
            ("skipped", "NONE"),
            (None, "NONE"),
        ],
    )
    def test_status_mapping(self, status, expected):
        item = {"head_pipeline": {"status": status}} if status else {}
        assert gitlab.parse_pipeline_status(item) == expected


class TestGitLabApiMapping:
    def test_list_open_merge_requests(self):
        payload = [{"iid": 7, "title": "Refactor"}]
        with patch(
            "graphify.gitlab.resolve_config",
            return_value=gitlab.GitLabConfig("https://gitlab.example.com", "g/p"),
        ), patch("graphify.gitlab._request", return_value=(payload, {})) as request:
            assert gitlab.list_open_merge_requests(limit=20) == payload
        assert request.call_args.args[1] == "/projects/g%2Fp/merge_requests"
        assert request.call_args.args[2]["state"] == "opened"

    def test_changed_files_follow_pagination_and_deduplicate(self):
        first = (
            [{"new_path": "src/a.py", "deleted_file": False}],
            {"X-Next-Page": "2"},
        )
        second = (
            [
                {"new_path": "src/a.py", "deleted_file": False},
                {"old_path": "src/deleted.py", "deleted_file": True},
            ],
            {"X-Next-Page": ""},
        )
        config = gitlab.GitLabConfig("https://gitlab.example.com", "g/p")
        with patch("graphify.gitlab.resolve_config", return_value=config), patch(
            "graphify.gitlab._request", side_effect=[first, second]
        ):
            files = gitlab.get_merge_request_files(9)
        assert files == ["src/a.py", "src/deleted.py"]

    def test_expand_submodule_diff_returns_prefixed_files(
        self, tmp_path, monkeypatch
    ):
        child = tmp_path / "modules" / "service"
        child.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        result = type(
            "Result",
            (),
            {"returncode": 0, "stdout": "src/a.py\nsrc/b.py\n"},
        )()
        diff = (
            "@@ -1 +1 @@\n"
            "-Subproject commit " + "a" * 40 + "\n"
            "+Subproject commit " + "b" * 40 + "\n"
        )
        with patch("graphify.gitlab.subprocess.run", return_value=result) as run:
            files = gitlab._expand_submodule_diff("modules/service", diff)
        assert files == [
            "modules/service/src/a.py",
            "modules/service/src/b.py",
        ]
        assert run.call_args.kwargs["stdin"] is gitlab.subprocess.DEVNULL

    def test_expand_submodule_diff_rejects_workspace_escape(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        diff = (
            "-Subproject commit " + "a" * 40 + "\n"
            "+Subproject commit " + "b" * 40 + "\n"
        )
        with patch("graphify.gitlab.subprocess.run") as run:
            assert gitlab._expand_submodule_diff("../outside", diff) == []
        run.assert_not_called()


class TestProviderDispatch:
    def test_fetch_prs_maps_gitlab_merge_request(self):
        payload = [{
            "iid": 42,
            "title": "Modernise persistence",
            "source_branch": "feature/refactor",
            "target_branch": "develop",
            "author": {"username": "alice"},
            "draft": False,
            "updated_at": "2026-07-23T10:00:00Z",
            "head_pipeline": {"status": "success"},
        }]
        with patch.dict(
            "os.environ", {"GRAPHIFY_VCS_PROVIDER": "gitlab"}, clear=False
        ), patch(
            "graphify.gitlab.list_open_merge_requests", return_value=payload
        ):
            changes = fetch_prs(base="develop")
        assert len(changes) == 1
        change = changes[0]
        assert change.number == 42
        assert change.provider == "gitlab"
        assert change.base_branch == "develop"
        assert change.ci_status == "SUCCESS"

    def test_fetch_pr_files_dispatches_to_gitlab(self):
        with patch.dict(
            "os.environ", {"GRAPHIFY_VCS_PROVIDER": "gitlab"}, clear=False
        ), patch(
            "graphify.gitlab.get_merge_request_files",
            return_value=["src/a.py"],
        ) as fetch:
            assert fetch_pr_files(42, "group/project") == ["src/a.py"]
        fetch.assert_called_once_with(42, "group/project")
