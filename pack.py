"""
experience.pack — create Experience Packets from raw execution episodes.

Usage:
    from experiencemd import pack

    packet = pack.from_episode(
        agent_id="agent-abc123",
        domain="oauth",
        task_family="redirect-uri-mismatch",
        task_goal="Fix OAuth login failure",
        environment={...},
        steps=[...],
        outcome="success",
        ...
    )
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from .schema import (
    EnvironmentSignature,
    ExperiencePacket,
    FailureStructure,
    Outcome,
    Provenance,
    Scenario,
    SolutionPath,
    SolutionStep,
    TaskOutcome,
    TransferableSkill,
    ValidationStatus,
)


# ─── Privacy scrubbing ───────────────────────────────────────────────────────

_PII_PATTERNS = [
    (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), "[EMAIL]"),
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), "[IP]"),
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I), "[UUID]"),
    (re.compile(r'(?i)(secret|password|token|key|credential)[=:\s]+\S+'), r"\1=[REDACTED]"),
    (re.compile(r'\b(?:https?://)[^\s/]+'), "[URL-HOST]"),
]

def scrub(text: str) -> str:
    """Remove PII and sensitive values from text before publishing."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

def scrub_dict(d: dict) -> dict:
    """Recursively scrub a dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, str):
            result[k] = scrub(v)
        elif isinstance(v, dict):
            result[k] = scrub_dict(v)
        elif isinstance(v, list):
            result[k] = [scrub(i) if isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result

def anonymise_agent_id(agent_id: str) -> str:
    """One-way hash of agent ID for privacy-preserving attribution."""
    return "agent-" + hashlib.sha256(agent_id.encode()).hexdigest()[:8]


# ─── Confidence scoring ──────────────────────────────────────────────────────

def _compute_confidence(
    outcome: TaskOutcome,
    retry_count: int,
    human_intervention: bool,
    steps_count: int,
    has_root_cause: bool,
    has_failed_attempts: bool,
) -> float:
    """
    Compute an initial confidence score for a new packet.

    Higher confidence when:
    - Task succeeded cleanly
    - Root cause was clearly identified
    - Low retries
    - No human intervention
    - Solution has multiple validated steps
    - Prior failed attempts were documented (shows learning)
    """
    score = 0.5

    if outcome == TaskOutcome.SUCCESS:
        score += 0.25
    elif outcome == TaskOutcome.PARTIAL:
        score += 0.05

    if has_root_cause:
        score += 0.10

    if has_failed_attempts:
        score += 0.05  # Documented learning

    if not human_intervention:
        score += 0.05

    retry_penalty = min(0.15, retry_count * 0.03)
    score -= retry_penalty

    if steps_count >= 3:
        score += 0.05

    return round(min(1.0, max(0.0, score)), 3)


# ─── Quality gate ────────────────────────────────────────────────────────────

class PackQualityError(ValueError):
    pass

def _quality_check(
    outcome: TaskOutcome,
    confidence: float,
    steps: list[dict],
    skill_statement: str,
    applicable_when: list[str],
    not_applicable_when: list[str],
) -> None:
    """Raise PackQualityError if packet doesn't meet minimum publishability bar."""
    if outcome == TaskOutcome.FAILURE:
        raise PackQualityError(
            "Cannot pack a failed episode. "
            "Only successful or partial outcomes produce publishable packets."
        )
    if confidence < 0.4:
        raise PackQualityError(
            f"Confidence score {confidence:.2f} is below minimum threshold (0.40). "
            "Resolve more clearly before packing."
        )
    if len(steps) < 2:
        raise PackQualityError("Minimum 2 solution steps required.")
    if not skill_statement.strip():
        raise PackQualityError("transferable_skill.skill_statement is required.")
    if not applicable_when:
        raise PackQualityError("transferable_skill.applicable_when must have at least one entry.")
    if not not_applicable_when:
        raise PackQualityError("transferable_skill.not_applicable_when must have at least one entry.")


# ─── Public API ──────────────────────────────────────────────────────────────

def from_episode(
    *,
    agent_id: str,
    domain: str,
    task_family: str,
    # Scenario
    task_goal: str,
    environment: dict[str, Any],
    observable_symptoms: list[str],
    tools_available: Optional[list[str]] = None,
    preconditions: Optional[list[str]] = None,
    # Failure
    failure_signature: str,
    confirmed_root_cause: str,
    misleading_signals: Optional[list[str]] = None,
    failed_attempts: Optional[list[str]] = None,
    # Solution
    steps: list[dict[str, Any]],
    why_it_worked: str,
    branching_logic: Optional[str] = None,
    recovery_path: Optional[str] = None,
    # Transferable skill
    skill_statement: str,
    applicable_when: list[str],
    not_applicable_when: list[str],
    adaptation_required: list[str],
    adaptation_hints: Optional[str] = None,
    prerequisites: Optional[list[str]] = None,
    # Outcome
    outcome: str = "success",
    time_to_resolve: Optional[int] = None,
    retry_count: int = 0,
    human_intervention: bool = False,
    confidence_after: float = 0.8,
    # Options
    scrub_pii: bool = True,
    raise_on_quality_fail: bool = True,
    evidence_references: Optional[list[str]] = None,
) -> ExperiencePacket:
    """
    Create an ExperiencePacket from a raw execution episode.

    This is the primary entry point for the pack module.

    Args:
        agent_id: Raw agent identifier (will be anonymised before storage).
        domain: High-level domain, e.g. "oauth", "browser-automation".
        task_family: Specific problem class, e.g. "redirect-uri-mismatch".
        task_goal: Plain language description of what was attempted.
        environment: Dict describing execution environment (mapped to EnvironmentSignature).
        observable_symptoms: What the agent observed that triggered this episode.
        failure_signature: Canonical label for the failure class.
        confirmed_root_cause: The actual cause, verified after resolution.
        steps: List of dicts with keys: action, tool_used (opt), rationale (opt),
               is_adaptation_point (opt, bool).
        why_it_worked: Explanation of the root cause resolution.
        skill_statement: One or two sentence abstracted pattern for Layer 3.
        applicable_when: List of conditions under which this skill applies.
        not_applicable_when: List of conditions under which it does not apply.
        adaptation_required: What must change per environment.
        outcome: "success" | "partial" | "failure".
        scrub_pii: If True, run PII scrubbing on text fields before packing.
        raise_on_quality_fail: If True, raise PackQualityError on quality check failure.
                               If False, return packet with low confidence.

    Returns:
        ExperiencePacket ready for storage and retrieval.

    Raises:
        PackQualityError: If the episode doesn't meet quality thresholds and
                          raise_on_quality_fail is True.
    """
    task_outcome = TaskOutcome(outcome)

    if scrub_pii:
        task_goal = scrub(task_goal)
        why_it_worked = scrub(why_it_worked)
        skill_statement = scrub(skill_statement)
        failure_signature = scrub(failure_signature)
        confirmed_root_cause = scrub(confirmed_root_cause)
        observable_symptoms = [scrub(s) for s in observable_symptoms]
        misleading_signals = [scrub(s) for s in (misleading_signals or [])]
        failed_attempts = [scrub(s) for s in (failed_attempts or [])]
        steps = [scrub_dict(s) for s in steps]
        environment = scrub_dict(environment)

    anon_agent_id = anonymise_agent_id(agent_id)

    solution_steps = [
        SolutionStep(
            step_id=i + 1,
            action=s["action"],
            tool_used=s.get("tool_used"),
            rationale=s.get("rationale"),
            is_adaptation_point=s.get("is_adaptation_point", False),
        )
        for i, s in enumerate(steps)
    ]

    confidence = _compute_confidence(
        outcome=task_outcome,
        retry_count=retry_count,
        human_intervention=human_intervention,
        steps_count=len(solution_steps),
        has_root_cause=bool(confirmed_root_cause),
        has_failed_attempts=bool(failed_attempts),
    )

    if raise_on_quality_fail:
        _quality_check(
            outcome=task_outcome,
            confidence=confidence,
            steps=steps,
            skill_statement=skill_statement,
            applicable_when=applicable_when,
            not_applicable_when=not_applicable_when,
        )

    env_sig_fields = {
        "protocol", "flow", "provider", "runtime", "config_surface", "app_type"
    }
    env_known = {k: v for k, v in environment.items() if k in env_sig_fields}
    env_custom = {k: v for k, v in environment.items() if k not in env_sig_fields}

    return ExperiencePacket.create(
        source_agent_id=anon_agent_id,
        domain=domain,
        task_family=task_family,
        confidence_score=confidence,
        scenario=Scenario(
            task_goal=task_goal,
            environment_signature=EnvironmentSignature(**env_known, custom=env_custom),
            observable_symptoms=observable_symptoms,
            tools_available=tools_available or [],
            preconditions=preconditions or [],
        ),
        failure=FailureStructure(
            failure_signature=failure_signature,
            confirmed_root_cause=confirmed_root_cause,
            misleading_signals=misleading_signals or [],
            failed_attempts=failed_attempts or [],
        ),
        solution=SolutionPath(
            steps=solution_steps,
            why_it_worked=why_it_worked,
            branching_logic=branching_logic,
            recovery_path=recovery_path,
        ),
        transferable_skill=TransferableSkill(
            skill_statement=skill_statement,
            applicable_when=applicable_when,
            not_applicable_when=not_applicable_when,
            adaptation_required=adaptation_required,
            adaptation_hints=adaptation_hints,
            prerequisites=prerequisites or [],
        ),
        outcome=Outcome(
            result=task_outcome,
            confidence_after=confidence_after,
            time_to_resolve=time_to_resolve,
            retry_count=retry_count,
            human_intervention=human_intervention,
        ),
        schema_version="0.1.0",
    )
