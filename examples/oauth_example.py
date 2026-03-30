"""
Full end-to-end example: OAuth redirect URI mismatch → Keycloak adaptation.

Demonstrates:
  1. Pack an experience from a real Azure AD episode
  2. Save to store
  3. Retrieve for a Keycloak problem
  4. Adapt to the Keycloak environment
  5. Simulate a trust update after use
  6. View store statistics
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from experiencemd import pack, ExperienceStore, ExperienceAdapter


def main():
    print("=" * 60)
    print("experience.md — End-to-End Example")
    print("=" * 60)

    # ── Step 1: Pack ──────────────────────────────────────────────

    print("\n[1] Packing Azure AD experience...")

    packet = pack.from_episode(
        agent_id="agent-production-007",
        domain="oauth",
        task_family="redirect-uri-mismatch",

        task_goal="Fix OAuth login failure — users authenticated but callback rejected",
        environment={
            "protocol": "OIDC",
            "flow": "auth-code",
            "provider": "azure-ad",
            "config_surface": "env-file",
            "app_type": "spa",
        },
        observable_symptoms=[
            "Token generation succeeds in auth provider logs",
            "Callback URL returns 401 or enters redirect loop",
            "No errors visible in auth provider dashboard",
        ],

        failure_signature="callback_uri_rejected_post_auth",
        confirmed_root_cause=(
            "Redirect URI mismatch between Azure App Registration "
            "and runtime env-file configuration"
        ),
        misleading_signals=[
            "Token generation appeared successful",
            "Auth provider showed no errors at token stage",
        ],
        failed_attempts=[
            "Checked and confirmed token scopes were correct",
            "Verified client ID was correct in both places",
        ],

        steps=[
            {
                "action": "Retrieve exact callback URL from runtime config",
                "rationale": "Get ground truth of what URL is actually being sent",
                "is_adaptation_point": False,
            },
            {
                "action": "Open Azure App Registration → Authentication → Redirect URIs",
                "tool_used": "browser",
                "rationale": "Compare registered URIs against runtime URL",
                "is_adaptation_point": True,
            },
            {
                "action": "Compare URIs character-by-character: scheme, host, path, trailing slash",
                "rationale": "OIDC requires exact string equality",
                "is_adaptation_point": False,
            },
            {
                "action": "Update env-file AZURE_REDIRECT_URI to exactly match registration",
                "is_adaptation_point": True,
            },
            {
                "action": "Re-test auth flow end-to-end in browser",
                "is_adaptation_point": False,
            },
        ],

        why_it_worked=(
            "OIDC spec requires exact URI equality. Even trailing slash differences "
            "cause the provider to reject the callback. The registration and runtime "
            "config are independent surfaces that can silently diverge."
        ),

        skill_statement=(
            "When auth partially succeeds but callback is rejected, verify exact "
            "redirect URI equality (scheme, host, path, trailing slash) between the "
            "provider registration console and the runtime configuration. These are "
            "independent surfaces that must match exactly."
        ),
        applicable_when=[
            "OIDC or OAuth2 auth-code flow",
            "Callback-based authentication",
            "Auth appears to succeed but callback fails or loops",
        ],
        not_applicable_when=[
            "Client credentials flow (no callback involved)",
            "Token scope or audience errors",
            "Provider-side rejections before token issuance",
        ],
        adaptation_required=[
            "Provider-specific registration console path",
            "Environment-specific config surface and variable names",
        ],
        adaptation_hints=(
            "Check provider-specific registration console and "
            "environment override files for the redirect URI setting."
        ),

        outcome="success",
        time_to_resolve=840,
        retry_count=2,
        human_intervention=False,
        confidence_after=0.94,
    )

    print(f"  Packed: {packet}")
    print(f"  Confidence: {packet.confidence_score}")
    print(f"  Trust: {packet.trust_score}")

    # ── Step 2: Save ──────────────────────────────────────────────

    print("\n[2] Saving to store...")
    store = ExperienceStore("./example_experience_db")
    store.save(packet)
    print(f"  Saved. Store stats: {store.stats()}")

    # ── Step 3: Retrieve ──────────────────────────────────────────

    print("\n[3] Retrieving for Keycloak redirect problem...")
    results = store.retrieve(
        query_env={
            "protocol": "OIDC",
            "flow": "auth-code",
            "provider": "keycloak",
            "config_surface": "k8s-secret",
            "app_type": "server",
        },
        task_context="keycloak redirect uri rejected after user login callback oauth",
        domain="oauth",
        task_family="redirect-uri-mismatch",   # known from problem classification
        top_k=3,
        min_score=0.30,                         # lower threshold for cross-env transfer
    )

    print(f"  Found {len(results)} result(s)")
    for r in results:
        print(f"  → {r}")

    if not results:
        print("  No results above threshold. Exiting.")
        return

    best = results[0]
    print(f"\n  Best match score: {best.score:.3f}")
    print(f"  Transferable skill: {best.packet.transferable_skill.skill_statement[:80]}...")

    # ── Step 4: Adapt ─────────────────────────────────────────────

    print("\n[4] Adapting to Keycloak + k8s-secret environment...")
    adapter = ExperienceAdapter()
    adapted = adapter.adapt(
        best.packet,
        target_env={
            "provider": "keycloak",
            "config_surface": "k8s-secret",
            "app_type": "server",
        },
    )

    print(f"\n{adapted.summary()}")
    print("\n  Adapted steps:")
    for step in adapted.adapted_steps:
        review_flag = " ← NEEDS REVIEW" if step["needs_review"] else ""
        adapted_flag = " [adapted]" if step["was_adapted"] else ""
        print(f"    {step['step_id']}. {step['action']}{adapted_flag}{review_flag}")

    print(f"\n  Adapted skill statement:")
    print(f"    {adapted.adapted_skill_statement[:100]}...")

    print(f"\n  Substitutions applied: {len(adapted.substitutions_applied)}")
    for find, replace in list(adapted.substitutions_applied.items())[:3]:
        print(f"    '{find}' → '{replace}'")

    if adapted.unmapped_fields:
        print(f"\n  Unmapped fields (need LLM or human review):")
        for field_name, change in adapted.unmapped_fields:
            print(f"    {field_name}: {change}")

    # ── Step 5: Trust update ──────────────────────────────────────

    print("\n[5] Simulating successful transfer — updating trust...")
    store.update_trust(
        packet_id=best.packet.experience_id,
        transfer_succeeded=True,
        attribution_score=0.75,
        retrieving_agent_id="agent-consumer-042",
        task_context="keycloak redirect URI mismatch in staging",
    )

    updated = store.get(best.packet.experience_id)
    print(f"  Updated trust score: {updated.trust_score:.3f}")
    print(f"  Reuse count: {updated.reuse_count}")

    # ── Step 6: Corroborate ───────────────────────────────────────

    print("\n[6] Corroborating packet...")
    store.corroborate(best.packet.experience_id, "agent-validator-001")
    store.corroborate(best.packet.experience_id, "agent-validator-002")
    corroborated = store.get(best.packet.experience_id)
    print(f"  Validation status: {corroborated.validation_status.value}")

    print("\n" + "=" * 60)
    print("Example complete.")
    print("experience_db written to ./example_experience_db/")
    print("=" * 60)


if __name__ == "__main__":
    main()
