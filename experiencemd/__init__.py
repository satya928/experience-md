"""
experiencemd — Python reference implementation of the experience.md standard.

The experience.md standard defines how AI agents can package, store, retrieve,
and adapt operational experience earned through real-world task execution.

Core objects:
    ExperiencePacket   — the atomic unit of transferable experience
    ExperienceStore    — persist and retrieve packets
    ExperienceAdapter  — adapt packets to target environments
    pack               — module for creating packets from raw episodes

Quick start:
    from experiencemd import pack, ExperienceStore, ExperienceAdapter

    # 1. Pack an experience
    packet = pack.from_episode(
        agent_id="my-agent",
        domain="oauth",
        task_family="redirect-uri-mismatch",
        task_goal="Fix OAuth login — callback rejected after auth",
        environment={"provider": "azure-ad", "flow": "auth-code",
                     "config_surface": "env-file", "app_type": "spa"},
        observable_symptoms=["Token generation succeeds", "Callback returns 401"],
        failure_signature="callback_uri_rejected_post_auth",
        confirmed_root_cause="Redirect URI mismatch between app registration and runtime",
        misleading_signals=["Token generation looked successful"],
        failed_attempts=["Checked token scopes", "Verified client ID"],
        steps=[
            {"action": "Retrieve exact callback URL from runtime config",
             "is_adaptation_point": False},
            {"action": "Open Azure App Registration → Authentication → Redirect URIs",
             "is_adaptation_point": True},
            {"action": "Compare URI character-by-character including trailing slash",
             "is_adaptation_point": False},
            {"action": "Update env-file AZURE_REDIRECT_URI to match registration exactly",
             "is_adaptation_point": True},
            {"action": "Re-test auth flow end-to-end", "is_adaptation_point": False},
        ],
        why_it_worked="OIDC requires exact URI equality — trailing slash matters",
        skill_statement=(
            "When auth partially succeeds but callback fails, verify exact redirect URI "
            "equality (scheme, host, path, trailing slash) between provider registration "
            "and runtime config. These are independent surfaces that must match exactly."
        ),
        applicable_when=["OIDC/OAuth2 auth-code flow", "Callback-based auth",
                         "Auth succeeds but callback is rejected"],
        not_applicable_when=["Client credentials flow", "Token scope errors"],
        adaptation_required=["Provider-specific registration console path",
                             "Environment config surface and variable names"],
        outcome="success",
        time_to_resolve=840,
        retry_count=2,
    )

    # 2. Save it
    store = ExperienceStore("./my_experience_db")
    store.save(packet)

    # 3. Retrieve for a Keycloak problem
    results = store.retrieve(
        query_env={"provider": "keycloak", "flow": "auth-code",
                   "config_surface": "k8s-secret"},
        task_context="keycloak redirect URI rejected after login",
        domain="oauth",
    )

    # 4. Adapt the best result
    adapter = ExperienceAdapter()
    adapted = adapter.adapt(
        results[0].packet,
        target_env={"provider": "keycloak", "config_surface": "k8s-secret"},
    )
    print(adapted.summary())

Schema version: 0.1.0
"""

__version__ = "0.1.0"
__schema_version__ = "0.1.0"
__author__ = "Quantum Agents Project"

from .schema import (
    ExperiencePacket,
    EnvironmentSignature,
    Scenario,
    FailureStructure,
    SolutionPath,
    SolutionStep,
    TransferableSkill,
    Variant,
    Outcome,
    Provenance,
    ProvenanceEntry,
    ValidationStatus,
    TaskOutcome,
)

from .store import ExperienceStore, RetrievalResult
from .adapt import ExperienceAdapter, AdaptationResult, EnvDiff
from . import pack

__all__ = [
    # Core objects
    "ExperiencePacket",
    "ExperienceStore",
    "ExperienceAdapter",
    "pack",
    # Schema types
    "EnvironmentSignature",
    "Scenario",
    "FailureStructure",
    "SolutionPath",
    "SolutionStep",
    "TransferableSkill",
    "Variant",
    "Outcome",
    "Provenance",
    "ProvenanceEntry",
    "ValidationStatus",
    "TaskOutcome",
    # Result types
    "RetrievalResult",
    "AdaptationResult",
    "EnvDiff",
]
