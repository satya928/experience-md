"""
experience.md schema — core dataclasses.

All fields match the experience.md v0.1.0 specification exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ValidationStatus(str, Enum):
    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    CORROBORATED = "corroborated"
    DEPRECATED = "deprecated"


class TaskOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


@dataclass
class EnvironmentSignature:
    """Structured descriptor of the execution environment."""
    protocol: Optional[str] = None        # e.g. "OIDC", "REST", "GraphQL"
    flow: Optional[str] = None            # e.g. "auth-code", "client-credentials"
    provider: Optional[str] = None        # e.g. "azure-ad", "keycloak", "cognito"
    runtime: Optional[str] = None         # e.g. "node18", "python311"
    config_surface: Optional[str] = None  # e.g. "env-file", "k8s-secret"
    app_type: Optional[str] = None        # e.g. "spa", "server", "mobile"
    custom: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v is not None and k != "custom"}
        d.update(self.custom)
        return d

    def similarity_keys(self) -> set[str]:
        return {f"{k}:{v}" for k, v in self.to_dict().items()}


@dataclass
class SolutionStep:
    """One step in the solution path."""
    step_id: int
    action: str
    tool_used: Optional[str] = None
    rationale: Optional[str] = None
    is_adaptation_point: bool = False     # Must this step change per environment?

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Scenario:
    task_goal: str
    environment_signature: EnvironmentSignature
    observable_symptoms: list[str]
    tools_available: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_goal": self.task_goal,
            "environment_signature": self.environment_signature.to_dict(),
            "observable_symptoms": self.observable_symptoms,
            "tools_available": self.tools_available,
            "preconditions": self.preconditions,
        }


@dataclass
class FailureStructure:
    failure_signature: str
    confirmed_root_cause: str
    misleading_signals: list[str] = field(default_factory=list)
    failed_attempts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class SolutionPath:
    steps: list[SolutionStep]
    why_it_worked: str
    branching_logic: Optional[str] = None
    recovery_path: Optional[str] = None

    def adaptation_points(self) -> list[SolutionStep]:
        return [s for s in self.steps if s.is_adaptation_point]

    def to_dict(self) -> dict:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "why_it_worked": self.why_it_worked,
            "branching_logic": self.branching_logic,
            "recovery_path": self.recovery_path,
        }


@dataclass
class TransferableSkill:
    """Layer 3 — the abstracted, transferable core of the experience."""
    skill_statement: str
    applicable_when: list[str]
    not_applicable_when: list[str]
    adaptation_required: list[str]
    adaptation_hints: Optional[str] = None
    prerequisites: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Variant:
    """Environment-specific execution path for the same underlying skill."""
    variant_id: str
    environment_signature: EnvironmentSignature
    overrides: dict[str, str]             # step_id → adapted action text
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "variant_id": self.variant_id,
            "environment_signature": self.environment_signature.to_dict(),
            "overrides": self.overrides,
            "notes": self.notes,
        }


@dataclass
class Outcome:
    result: TaskOutcome
    confidence_after: float               # 0.0–1.0
    time_to_resolve: Optional[int] = None # seconds
    retry_count: Optional[int] = None
    human_intervention: bool = False

    def to_dict(self) -> dict:
        return {
            "result": self.result.value,
            "confidence_after": self.confidence_after,
            "time_to_resolve": self.time_to_resolve,
            "retry_count": self.retry_count,
            "human_intervention": self.human_intervention,
        }


@dataclass
class ProvenanceEntry:
    """One record of a packet being retrieved and used."""
    agent_id: str
    task_context: str
    outcome: TaskOutcome
    attribution_score: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "task_context": self.task_context,
            "outcome": self.outcome.value,
            "attribution_score": self.attribution_score,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Provenance:
    evidence_references: list[str] = field(default_factory=list)
    corroborated_by: list[str] = field(default_factory=list)
    prior_reuse_log: list[ProvenanceEntry] = field(default_factory=list)
    lineage: Optional[str] = None         # parent packet ID

    def to_dict(self) -> dict:
        return {
            "evidence_references": self.evidence_references,
            "corroborated_by": self.corroborated_by,
            "prior_reuse_log": [e.to_dict() for e in self.prior_reuse_log],
            "lineage": self.lineage,
        }


@dataclass
class ExperiencePacket:
    """
    The atomic unit of the experience.md standard.

    Three layers:
      1. scenario       — what was the situation
      2. failure + solution — what happened and what was done
      3. transferable_skill — what generalises across environments
    """
    # Metadata
    experience_id: str
    schema_version: str
    created_at: datetime
    source_agent_id: str
    domain: str
    task_family: str
    confidence_score: float
    validation_status: ValidationStatus

    # Content layers
    scenario: Scenario
    failure: FailureStructure
    solution: SolutionPath
    transferable_skill: TransferableSkill
    outcome: Outcome

    # Optional
    variants: list[Variant] = field(default_factory=list)
    provenance: Provenance = field(default_factory=Provenance)
    reuse_count: int = 0
    trust_score: float = 0.5

    @classmethod
    def create(
        cls,
        source_agent_id: str,
        domain: str,
        task_family: str,
        scenario: Scenario,
        failure: FailureStructure,
        solution: SolutionPath,
        transferable_skill: TransferableSkill,
        outcome: Outcome,
        confidence_score: float = 0.7,
        schema_version: str = "0.1.0",
    ) -> "ExperiencePacket":
        """Factory: create a new packet with generated ID and timestamp."""
        return cls(
            experience_id=str(uuid.uuid4()),
            schema_version=schema_version,
            created_at=datetime.now(timezone.utc),
            source_agent_id=source_agent_id,
            domain=domain,
            task_family=task_family,
            confidence_score=confidence_score,
            validation_status=ValidationStatus.UNVALIDATED,
            scenario=scenario,
            failure=failure,
            solution=solution,
            transferable_skill=transferable_skill,
            outcome=outcome,
        )

    def to_dict(self) -> dict:
        return {
            "experience_id": self.experience_id,
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "source_agent_id": self.source_agent_id,
            "domain": self.domain,
            "task_family": self.task_family,
            "confidence_score": self.confidence_score,
            "validation_status": self.validation_status.value,
            "reuse_count": self.reuse_count,
            "trust_score": self.trust_score,
            "scenario": self.scenario.to_dict(),
            "failure": self.failure.to_dict(),
            "solution": self.solution.to_dict(),
            "transferable_skill": self.transferable_skill.to_dict(),
            "variants": [v.to_dict() for v in self.variants],
            "outcome": self.outcome.to_dict(),
            "provenance": self.provenance.to_dict(),
        }

    def __repr__(self) -> str:
        return (
            f"ExperiencePacket(id={self.experience_id[:8]}..., "
            f"domain={self.domain}, family={self.task_family}, "
            f"status={self.validation_status.value}, "
            f"trust={self.trust_score:.2f})"
        )
