"""Tests for the experiencemd library."""

import sys, os, shutil, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiencemd import pack, ExperienceStore, ExperienceAdapter
from experiencemd.schema import TaskOutcome, ValidationStatus
from experiencemd.pack import PackQualityError, scrub, anonymise_agent_id
from experiencemd.adapt import diff_environments, build_substitution_map
from experiencemd.schema import EnvironmentSignature


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_packet(**overrides):
    defaults = dict(
        agent_id="test-agent-001",
        domain="oauth",
        task_family="redirect-uri-mismatch",
        task_goal="Fix OAuth callback failure",
        environment={"provider": "azure-ad", "flow": "auth-code",
                     "config_surface": "env-file", "app_type": "spa"},
        observable_symptoms=["Callback returns 401"],
        failure_signature="callback_uri_rejected_post_auth",
        confirmed_root_cause="URI mismatch",
        steps=[
            {"action": "Check runtime callback URL", "is_adaptation_point": False},
            {"action": "Open Azure App Registration → Redirect URIs",
             "is_adaptation_point": True},
            {"action": "Update env-file AZURE_REDIRECT_URI", "is_adaptation_point": True},
        ],
        why_it_worked="OIDC requires exact equality",
        skill_statement="Verify exact URI equality between registration and runtime.",
        applicable_when=["auth-code flow", "callback-based auth"],
        not_applicable_when=["client-credentials", "scope errors"],
        adaptation_required=["Provider console path", "Config variable names"],
        outcome="success",
    )
    defaults.update(overrides)
    return pack.from_episode(**defaults)


# ── Pack tests ────────────────────────────────────────────────────────────────

def test_pack_creates_packet():
    p = _make_packet()
    assert p.experience_id
    assert p.domain == "oauth"
    assert p.task_family == "redirect-uri-mismatch"
    assert p.outcome.result == TaskOutcome.SUCCESS
    assert p.validation_status == ValidationStatus.UNVALIDATED
    print("PASS test_pack_creates_packet")


def test_pack_anonymises_agent_id():
    p = _make_packet(agent_id="real-agent-name")
    assert "real-agent-name" not in p.source_agent_id
    assert p.source_agent_id.startswith("agent-")
    print("PASS test_pack_anonymises_agent_id")


def test_pack_quality_check_rejects_failure():
    try:
        _make_packet(outcome="failure")
        assert False, "Should have raised PackQualityError"
    except PackQualityError as e:
        assert "failed episode" in str(e).lower()
    print("PASS test_pack_quality_check_rejects_failure")


def test_pack_quality_check_rejects_too_few_steps():
    try:
        _make_packet(steps=[{"action": "only one step", "is_adaptation_point": False}])
        assert False, "Should have raised PackQualityError"
    except PackQualityError as e:
        assert "2" in str(e)
    print("PASS test_pack_quality_check_rejects_too_few_steps")


def test_pack_scrubs_pii():
    p = _make_packet(
        task_goal="Fix OAuth for user@example.com on 192.168.1.1",
        scrub_pii=True,
    )
    assert "user@example.com" not in p.scenario.task_goal
    assert "192.168.1.1" not in p.scenario.task_goal
    assert "[EMAIL]" in p.scenario.task_goal
    assert "[IP]" in p.scenario.task_goal
    print("PASS test_pack_scrubs_pii")


def test_pack_confidence_high_for_clean_success():
    p = _make_packet(retry_count=0, human_intervention=False)
    assert p.confidence_score >= 0.7
    print("PASS test_pack_confidence_high_for_clean_success")


def test_pack_confidence_lower_with_retries():
    p_clean = _make_packet(retry_count=0)
    p_retried = _make_packet(retry_count=5)
    assert p_retried.confidence_score < p_clean.confidence_score
    print("PASS test_pack_confidence_lower_with_retries")


# ── Store tests ───────────────────────────────────────────────────────────────

def test_store_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExperienceStore(tmpdir)
        p = _make_packet()
        store.save(p)
        assert p.experience_id in store.list_ids()

        results = store.retrieve(
            query_env={"provider": "azure-ad", "flow": "auth-code"},
            task_context="OAuth callback rejected after login redirect uri mismatch",
            domain="oauth",
            task_family="redirect-uri-mismatch",
        )
        assert len(results) > 0
        assert results[0].packet.experience_id == p.experience_id
    print("PASS test_store_save_and_retrieve")


def test_store_retrieval_scores_above_threshold():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExperienceStore(tmpdir)
        store.save(_make_packet())

        results = store.retrieve(
            query_env={"provider": "completely-different-provider"},
            task_context="something totally unrelated to oauth",
            domain="browser-automation",
        )
        assert len(results) == 0  # Should be filtered by domain + low score
    print("PASS test_store_retrieval_domain_filter")


def test_store_trust_update():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExperienceStore(tmpdir)
        p = _make_packet()
        initial_trust = p.trust_score
        store.save(p)

        store.update_trust(
            packet_id=p.experience_id,
            transfer_succeeded=True,
            attribution_score=0.85,
            retrieving_agent_id="agent-consumer",
            task_context="test context",
        )

        updated = store.get(p.experience_id)
        assert updated.reuse_count == 1
        assert len(updated.provenance.prior_reuse_log) == 1
    print("PASS test_store_trust_update")


def test_store_corroboration_upgrades_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ExperienceStore(tmpdir)
        p = _make_packet()
        store.save(p)

        assert p.validation_status == ValidationStatus.UNVALIDATED
        store.corroborate(p.experience_id, "agent-a")
        assert store.get(p.experience_id).validation_status == ValidationStatus.VALIDATED
        store.corroborate(p.experience_id, "agent-b")
        assert store.get(p.experience_id).validation_status == ValidationStatus.CORROBORATED
    print("PASS test_store_corroboration_upgrades_status")


def test_store_persistence_across_instances():
    with tempfile.TemporaryDirectory() as tmpdir:
        store1 = ExperienceStore(tmpdir)
        p = _make_packet()
        store1.save(p)

        store2 = ExperienceStore(tmpdir)  # New instance, same dir
        assert p.experience_id in store2.list_ids()
        loaded = store2.get(p.experience_id)
        assert loaded.task_family == p.task_family
    print("PASS test_store_persistence_across_instances")


# ── Adapt tests ───────────────────────────────────────────────────────────────

def test_adapt_env_diff():
    source = EnvironmentSignature(provider="azure-ad", config_surface="env-file")
    target = {"provider": "keycloak", "config_surface": "k8s-secret"}
    diff = diff_environments(source, target)

    assert "provider" in diff.changed_fields
    assert diff.changed_fields["provider"] == ("azure-ad", "keycloak")
    assert "config_surface" in diff.changed_fields
    print("PASS test_adapt_env_diff")


def test_adapt_substitution_map():
    source = EnvironmentSignature(provider="azure-ad", config_surface="env-file")
    target = {"provider": "keycloak", "config_surface": "k8s-secret"}
    diff = diff_environments(source, target)
    subs, unmapped = build_substitution_map(diff)

    assert len(subs) > 0
    assert "Azure App Registration" in subs
    assert "Keycloak" in subs["Azure App Registration"]
    print("PASS test_adapt_substitution_map")


def test_adapt_applies_substitutions_to_adaptation_points():
    p = _make_packet()
    adapter = ExperienceAdapter()
    result = adapter.adapt(
        p,
        target_env={"provider": "keycloak", "config_surface": "k8s-secret"},
    )

    adapted_actions = [s["action"] for s in result.adapted_steps if s["was_adapted"]]
    assert any("Keycloak" in a or "keycloak" in a.lower() for a in adapted_actions)
    print("PASS test_adapt_applies_substitutions_to_adaptation_points")


def test_adapt_non_adaptation_steps_unchanged():
    p = _make_packet()
    adapter = ExperienceAdapter()
    result = adapter.adapt(
        p,
        target_env={"provider": "keycloak", "config_surface": "k8s-secret"},
    )

    for step in result.adapted_steps:
        if not step["was_adapted"]:
            assert step["action"] == step["original_action"]
    print("PASS test_adapt_non_adaptation_steps_unchanged")


def test_adapt_confidence_decreases_with_unmapped():
    p = _make_packet()
    adapter = ExperienceAdapter()

    result_close = adapter.adapt(
        p, target_env={"provider": "keycloak"}
    )
    result_far = adapter.adapt(
        p, target_env={"provider": "completely-unknown-provider-xyz"}
    )

    assert result_far.confidence <= result_close.confidence
    print("PASS test_adapt_confidence_decreases_with_unmapped")


# ── Scrub tests ───────────────────────────────────────────────────────────────

def test_scrub_email():
    assert "[EMAIL]" in scrub("contact user@example.com now")

def test_scrub_ip():
    assert "[IP]" in scrub("server at 10.0.0.1 is down")

def test_scrub_leaves_normal_text():
    text = "Check the redirect URI in the admin console"
    assert scrub(text) == text

def test_anonymise_agent_id_deterministic():
    assert anonymise_agent_id("my-agent") == anonymise_agent_id("my-agent")

def test_anonymise_agent_id_different_inputs():
    assert anonymise_agent_id("agent-a") != anonymise_agent_id("agent-b")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_pack_creates_packet,
        test_pack_anonymises_agent_id,
        test_pack_quality_check_rejects_failure,
        test_pack_quality_check_rejects_too_few_steps,
        test_pack_scrubs_pii,
        test_pack_confidence_high_for_clean_success,
        test_pack_confidence_lower_with_retries,
        test_store_save_and_retrieve,
        test_store_retrieval_scores_above_threshold,
        test_store_trust_update,
        test_store_corroboration_upgrades_status,
        test_store_persistence_across_instances,
        test_adapt_env_diff,
        test_adapt_substitution_map,
        test_adapt_applies_substitutions_to_adaptation_points,
        test_adapt_non_adaptation_steps_unchanged,
        test_adapt_confidence_decreases_with_unmapped,
        test_scrub_email,
        test_scrub_ip,
        test_scrub_leaves_normal_text,
        test_anonymise_agent_id_deterministic,
        test_anonymise_agent_id_different_inputs,
    ]

    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
