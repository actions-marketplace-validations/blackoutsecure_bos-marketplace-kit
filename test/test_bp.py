"""Unit tests for the branch-protection helper module.

The module under test is shipped *inside* the
`.github/actions/branch-protection/` directory so the composite is
self-contained for external consumers. It is loaded by `conftest.py`
under the alias ``bp_helper``.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import bp_helper as bp  # type: ignore[import-not-found]  # noqa: E402

# ---------------------------------------------------------------------------
# parse_status_checks
# ---------------------------------------------------------------------------

class TestParseStatusChecks:
    def test_empty_returns_empty_list(self) -> None:
        assert bp.parse_status_checks("") == []
        assert bp.parse_status_checks("   ") == []

    def test_csv(self) -> None:
        assert bp.parse_status_checks("a,b,c") == [
            {"context": "a", "app_id": None},
            {"context": "b", "app_id": None},
            {"context": "c", "app_id": None},
        ]

    def test_newline_separated(self) -> None:
        assert bp.parse_status_checks("a\nb") == [
            {"context": "a", "app_id": None},
            {"context": "b", "app_id": None},
        ]

    def test_dedupes_in_order(self) -> None:
        assert bp.parse_status_checks("a,b,a,c,b") == [
            {"context": "a", "app_id": None},
            {"context": "b", "app_id": None},
            {"context": "c", "app_id": None},
        ]

    def test_strips_whitespace(self) -> None:
        assert bp.parse_status_checks("  a  ,  b  ") == [
            {"context": "a", "app_id": None},
            {"context": "b", "app_id": None},
        ]


# ---------------------------------------------------------------------------
# parse_restrict_pushes
# ---------------------------------------------------------------------------

class TestParseRestrictPushes:
    def test_empty_returns_none(self) -> None:
        assert bp.parse_restrict_pushes("") is None
        assert bp.parse_restrict_pushes("   ") is None
        assert bp.parse_restrict_pushes(None) is None  # type: ignore[arg-type]

    def test_users_only(self) -> None:
        assert bp.parse_restrict_pushes("alice,bob") == {
            "users": ["alice", "bob"],
            "teams": [],
            "apps": [],
        }

    def test_team_prefix(self) -> None:
        assert bp.parse_restrict_pushes("team:reviewers,team:owners") == {
            "users": [],
            "teams": ["reviewers", "owners"],
            "apps": [],
        }

    def test_app_prefix(self) -> None:
        assert bp.parse_restrict_pushes("app:dependabot,app:release-bot") == {
            "users": [],
            "teams": [],
            "apps": ["dependabot", "release-bot"],
        }

    def test_mixed(self) -> None:
        out = bp.parse_restrict_pushes("alice,team:r,app:bot,bob")
        assert out == {
            "users": ["alice", "bob"],
            "teams": ["r"],
            "apps": ["bot"],
        }

    def test_strips_whitespace(self) -> None:
        assert bp.parse_restrict_pushes(" alice , team:r ") == {
            "users": ["alice"],
            "teams": ["r"],
            "apps": [],
        }


# ---------------------------------------------------------------------------
# build_payload
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_defaults_match_recommended_marketplace_policy(self) -> None:
        """All bp_* unset → kit defaults applied (the recommended
        Marketplace baseline)."""
        p = bp.build_payload(env={})
        # PR reviews enabled with 1 approval + stale dismiss + codeowners.
        assert p["required_pull_request_reviews"] == {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 1,
            "require_last_push_approval": False,
        }
        # required_status_checks present with strict=true (matches default).
        assert p["required_status_checks"] == {"strict": True, "checks": []}
        # Force-push + delete disallowed.
        assert p["allow_force_pushes"] is False
        assert p["allow_deletions"] is False
        # Convo resolution + linear history on.
        assert p["required_conversation_resolution"] is True
        assert p["required_linear_history"] is True
        # Signed commits + lock-branch opt-in (off by default).
        assert p["required_signatures"] is False
        assert p["lock_branch"] is False
        # Admins not enforced by default (solo-maintainer friendly).
        assert p["enforce_admins"] is False
        # No restrictions by default.
        assert p["restrictions"] is None

    def test_disable_pr_review_collapses_to_null(self) -> None:
        p = bp.build_payload(env={"BP_REQUIRE_PR": "false"})
        assert p["required_pull_request_reviews"] is None

    def test_status_check_strict_off_drops_required_status_checks(self) -> None:
        # If strict=false AND no checks supplied → required_status_checks=None
        p = bp.build_payload(env={"BP_STATUS_CHECKS_STRICT": "false"})
        assert p["required_status_checks"] is None

    def test_status_check_contexts_listed(self) -> None:
        p = bp.build_payload(env={"BP_STATUS_CHECKS": "build,test"})
        assert p["required_status_checks"]["checks"] == [
            {"context": "build", "app_id": None},
            {"context": "test", "app_id": None},
        ]

    def test_no_force_push_inverted(self) -> None:
        # bp_no_force_push=true → allow_force_pushes=false
        assert bp.build_payload(env={"BP_NO_FORCE_PUSH": "true"})["allow_force_pushes"] is False
        assert bp.build_payload(env={"BP_NO_FORCE_PUSH": "false"})["allow_force_pushes"] is True

    def test_no_deletion_inverted(self) -> None:
        assert bp.build_payload(env={"BP_NO_DELETION": "true"})["allow_deletions"] is False
        assert bp.build_payload(env={"BP_NO_DELETION": "false"})["allow_deletions"] is True

    def test_approval_count_coerced_from_string(self) -> None:
        p = bp.build_payload(env={"BP_REQUIRED_APPROVALS": "3"})
        assert p["required_pull_request_reviews"]["required_approving_review_count"] == 3

    def test_approval_count_garbage_falls_back_to_default(self) -> None:
        p = bp.build_payload(env={"BP_REQUIRED_APPROVALS": "not-a-number"})
        assert p["required_pull_request_reviews"]["required_approving_review_count"] == 1

    def test_restrict_pushes_propagates(self) -> None:
        p = bp.build_payload(env={"BP_RESTRICT_PUSHES": "alice,team:r"})
        assert p["restrictions"] == {
            "users": ["alice"],
            "teams": ["r"],
            "apps": [],
        }

    def test_payload_serialises_to_json(self) -> None:
        # Sanity: the dict must be JSON-encodable (the API consumer
        # will encode it via curl -d).
        p = bp.build_payload(env={})
        assert json.loads(json.dumps(p)) == p


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------

def _full_desired() -> dict:
    """A representative desired payload mirroring the kit defaults."""
    return bp.build_payload(env={})


class TestCompare:
    def test_empty_current_reports_drift_everywhere(self) -> None:
        """An unprotected branch (GET returns {}) drifts on every
        asserted setting."""
        des = _full_desired()
        findings = bp.compare(des, {})
        joined = "\n".join(findings)
        # PR review checks (4 keys) should each be reported.
        for k in (
            "dismiss_stale_reviews",
            "require_code_owner_reviews",
            "required_approving_review_count",
            "require_last_push_approval",
        ):
            assert f"required_pull_request_reviews.{k}" in joined
        # Linear history + conversation resolution should drift.
        assert "required_linear_history" in joined
        assert "required_conversation_resolution" in joined

    def test_compliant_returns_empty_list(self) -> None:
        """If GET returns the same state as desired, no drift."""
        des = _full_desired()
        # Simulate the GET response shape — booleans come back as
        # {"enabled": bool} for several keys.
        current = {
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": True,
                "required_approving_review_count": 1,
                "require_last_push_approval": False,
            },
            "required_status_checks": {
                "strict": True,
                "checks": [],
            },
            "enforce_admins": {"enabled": False},
            "required_linear_history": {"enabled": True},
            "required_conversation_resolution": {"enabled": True},
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
            "lock_branch": {"enabled": False},
            "required_signatures": {"enabled": False},
        }
        assert bp.compare(des, current) == []

    def test_diff_only_for_drifted_field(self) -> None:
        des = _full_desired()
        current = {
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": True,
                "required_approving_review_count": 1,
                "require_last_push_approval": False,
            },
            "required_status_checks": {"strict": True, "checks": []},
            "enforce_admins": {"enabled": False},
            "required_linear_history": {"enabled": True},
            "required_conversation_resolution": {"enabled": True},
            # Drift here.
            "allow_force_pushes": {"enabled": True},
            "allow_deletions": {"enabled": False},
            "lock_branch": {"enabled": False},
            "required_signatures": {"enabled": False},
        }
        findings = bp.compare(des, current)
        assert len(findings) == 1
        assert "allow_force_pushes: want=False got=True" in findings[0]

    def test_status_check_contexts_diff(self) -> None:
        des = bp.build_payload(env={"BP_STATUS_CHECKS": "build,test"})
        current = {
            "required_status_checks": {
                "strict": True,
                "checks": [{"context": "build", "app_id": None}],
            },
        }
        findings = bp.compare(des, current)
        assert any("required_status_checks.checks" in f for f in findings)

    def test_pr_review_disabled_with_enabled_current_drifts(self) -> None:
        # Synthesise a desired payload that *only* asserts "no PR reviews"
        # to keep the test focused on that single rule.
        des = {"required_pull_request_reviews": None}
        current = {
            "required_pull_request_reviews": {
                "required_approving_review_count": 1,
            },
        }
        findings = bp.compare(des, current)
        assert findings == [
            "required_pull_request_reviews: want=disabled got=enabled"
        ]


# ---------------------------------------------------------------------------
# CLI shim
# ---------------------------------------------------------------------------

class TestCli:
    def test_build_subcommand_emits_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bp.main(["build"])
        assert rc == 0
        d = json.loads(buf.getvalue())
        assert "required_pull_request_reviews" in d

    def test_build_pretty_flag(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bp.main(["build", "--pretty"])
        assert rc == 0
        # Pretty output is multi-line.
        assert buf.getvalue().count("\n") > 5

    def test_parse_restrict_subcommand(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bp.main(["parse-restrict", "--spec", "alice,team:r"])
        assert rc == 0
        d = json.loads(buf.getvalue())
        assert d == {"users": ["alice"], "teams": ["r"], "apps": []}

    def test_parse_restrict_empty_emits_null(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bp.main(["parse-restrict", "--spec", ""])
        assert rc == 0
        assert json.loads(buf.getvalue()) is None

    def test_compare_subcommand(self, tmp_path: Path) -> None:
        des_file = tmp_path / "des.json"
        cur_file = tmp_path / "cur.json"
        des_file.write_text(json.dumps(_full_desired()))
        cur_file.write_text("{}")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bp.main(["compare", "--desired", str(des_file), "--current", str(cur_file)])
        assert rc == 0
        out = buf.getvalue()
        assert "__COMPLIANT__" not in out
        assert "required_pull_request_reviews" in out

    def test_compare_compliant(self, tmp_path: Path) -> None:
        # Both files have identical empty payloads → "compliant".
        des_file = tmp_path / "des.json"
        cur_file = tmp_path / "cur.json"
        des_file.write_text("{}")
        cur_file.write_text("{}")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bp.main(["compare", "--desired", str(des_file), "--current", str(cur_file)])
        assert rc == 0
        assert buf.getvalue().strip() == "__COMPLIANT__"
