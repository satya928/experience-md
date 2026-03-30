"""
experience.store — persist and retrieve Experience Packets.

Provides a file-backed store with multi-factor similarity scoring.
Swap the backend by subclassing ExperienceStore.

Usage:
    from experiencemd import ExperienceStore

    store = ExperienceStore("./experience_db")
    store.save(packet)

    results = store.retrieve(
        query_env={"provider": "keycloak", "flow": "auth-code"},
        task_context="callback rejected after login",
        domain="oauth",
        top_k=5,
    )
"""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .schema import (
    EnvironmentSignature,
    ExperiencePacket,
    ProvenanceEntry,
    TaskOutcome,
    ValidationStatus,
)


# ─── Retrieval scoring ───────────────────────────────────────────────────────

RETRIEVAL_WEIGHTS = {
    "task_family":   0.30,
    "failure_sig":   0.25,
    "environment":   0.20,
    "tools":         0.10,
    "trust":         0.10,
    "recency":       0.05,
}

MINIMUM_SCORE = 0.35    # Packets below this are withheld even if top-ranked
DEFAULT_TOP_K = 5


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _text_token_similarity(a: str, b: str) -> float:
    """Simple token-overlap similarity — production would use embeddings."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    return _jaccard(tokens_a, tokens_b)


def _env_similarity(packet_env: EnvironmentSignature, query_env: dict) -> float:
    """Jaccard similarity over environment signature key:value pairs."""
    packet_keys = packet_env.similarity_keys()
    query_keys = {f"{k}:{v}" for k, v in query_env.items()}
    return _jaccard(packet_keys, query_keys)


def _recency_score(created_at: datetime, domain: str) -> float:
    """
    Domain-aware recency score (0.0–1.0).
    Technical patterns have long half-lives; market patterns decay fast.
    """
    now = datetime.now(timezone.utc)
    age_days = (now - created_at).days

    half_life_days = {
        "oauth": 180,
        "browser-automation": 60,
        "api-integration": 120,
        "devops": 90,
        "default": 120,
    }.get(domain, 120)

    return math.exp(-0.693 * age_days / half_life_days)


def score_packet(
    packet: ExperiencePacket,
    query_env: dict,
    task_context: str,
    domain: Optional[str],
    task_family: Optional[str],
) -> float:
    """
    Compute retrieval score for one packet against a query context.

    S = w1*task_family + w2*failure_sig + w3*env + w4*tools + w5*trust + w6*recency
    """
    w = RETRIEVAL_WEIGHTS

    # Task family — when no hint, compare task_context against multiple packet signals
    if task_family and packet.task_family == task_family:
        task_fam_score = 1.0
    elif task_family:
        task_fam_score = _text_token_similarity(packet.task_family, task_family)
    else:
        # Broad match: best of family, task_goal, and skill_statement vs context
        fam_sim = _text_token_similarity(packet.task_family, task_context)
        goal_sim = _text_token_similarity(packet.scenario.task_goal, task_context)
        skill_sim = _text_token_similarity(
            packet.transferable_skill.skill_statement, task_context
        )
        symptom_sim = max(
            (_text_token_similarity(s, task_context)
             for s in packet.scenario.observable_symptoms),
            default=0.0,
        )
        task_fam_score = max(fam_sim, goal_sim * 0.8, skill_sim * 0.7, symptom_sim * 0.9)

    # Failure signature — compare against full task context
    fail_score = max(
        _text_token_similarity(packet.failure.failure_signature, task_context),
        _text_token_similarity(packet.failure.confirmed_root_cause, task_context),
    )

    # Environment similarity
    env_score = _env_similarity(packet.scenario.environment_signature, query_env)

    # Tool similarity
    query_tools = set(query_env.get("tools_available", []))
    packet_tools = set(packet.scenario.tools_available)
    tool_score = _jaccard(query_tools, packet_tools) if query_tools else 0.5

    # Trust score (already 0.0–1.0)
    trust_score = packet.trust_score

    # Recency
    recency = _recency_score(packet.created_at, packet.domain)

    # Domain filter — hard filter if domain specified and doesn't match
    if domain and packet.domain != domain:
        return 0.0

    # Validation status boost
    validation_boost = {
        ValidationStatus.CORROBORATED: 1.10,
        ValidationStatus.VALIDATED:    1.05,
        ValidationStatus.UNVALIDATED:  1.00,
        ValidationStatus.DEPRECATED:   0.00,
    }.get(packet.validation_status, 1.0)

    raw = (
        w["task_family"] * task_fam_score
        + w["failure_sig"] * fail_score
        + w["environment"] * env_score
        + w["tools"] * tool_score
        + w["trust"] * trust_score
        + w["recency"] * recency
    )

    return round(raw * validation_boost, 4)


# ─── Retrieval result ────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    packet: ExperiencePacket
    score: float
    score_breakdown: dict[str, float]

    def __repr__(self) -> str:
        return (
            f"RetrievalResult(score={self.score:.3f}, "
            f"packet={self.packet.experience_id[:8]}..., "
            f"family={self.packet.task_family})"
        )


# ─── Store ───────────────────────────────────────────────────────────────────

class ExperienceStore:
    """
    File-backed Experience Packet store.

    Each packet is stored as a JSON file under {root}/{domain}/{packet_id}.json.
    An in-memory index is built on load for fast retrieval.

    For production use, replace _load / _persist with a vector DB backend.
    The retrieval interface (retrieve, save, update_trust) remains identical.
    """

    def __init__(self, root: str = "./experience_db"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, ExperiencePacket] = {}
        self._load_all()

    # ── Persistence ──────────────────────────────────────────────

    def _packet_path(self, packet: ExperiencePacket) -> Path:
        domain_dir = self.root / packet.domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        return domain_dir / f"{packet.experience_id}.json"

    def _persist(self, packet: ExperiencePacket) -> None:
        path = self._packet_path(packet)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(packet.to_dict(), f, indent=2, default=str)

    def _load_all(self) -> None:
        """Load all packets from disk into the in-memory index."""
        for json_path in self.root.rglob("*.json"):
            try:
                with open(json_path, encoding="utf-8") as f:
                    data = json.load(f)
                packet = _packet_from_dict(data)
                self._index[packet.experience_id] = packet
            except Exception:
                pass  # Skip malformed files silently

    # ── Write ─────────────────────────────────────────────────────

    def save(self, packet: ExperiencePacket) -> None:
        """Persist a new packet. Overwrites if ID already exists."""
        self._index[packet.experience_id] = packet
        self._persist(packet)

    def delete(self, packet_id: str) -> bool:
        """Remove a packet. Returns True if found and deleted."""
        if packet_id not in self._index:
            return False
        packet = self._index.pop(packet_id)
        path = self._packet_path(packet)
        if path.exists():
            path.unlink()
        return True

    def deprecate(self, packet_id: str) -> None:
        """Mark a packet as deprecated (it stays in store but scores 0)."""
        if packet_id in self._index:
            self._index[packet_id].validation_status = ValidationStatus.DEPRECATED
            self._persist(self._index[packet_id])

    # ── Trust updates ─────────────────────────────────────────────

    def update_trust(
        self,
        packet_id: str,
        transfer_succeeded: bool,
        attribution_score: float,
        retrieving_agent_id: str,
        task_context: str,
    ) -> None:
        """
        Update trust score after a retrieval use.

        Trust increases on successful use, decreases on failure.
        Persists the updated packet.
        """
        if packet_id not in self._index:
            return

        packet = self._index[packet_id]

        # Update reuse count and provenance log
        packet.reuse_count += 1
        entry = ProvenanceEntry(
            agent_id=retrieving_agent_id,
            task_context=task_context,
            outcome=TaskOutcome.SUCCESS if transfer_succeeded else TaskOutcome.FAILURE,
            attribution_score=attribution_score,
        )
        packet.provenance.prior_reuse_log.append(entry)

        # Recompute trust from reuse history
        log = packet.provenance.prior_reuse_log
        if log:
            success_rate = sum(
                1 for e in log if e.outcome == TaskOutcome.SUCCESS
            ) / len(log)
            avg_attribution = sum(e.attribution_score for e in log) / len(log)
            packet.trust_score = round(
                packet.confidence_score * 0.4
                + success_rate * 0.4
                + avg_attribution * 0.2,
                3
            )

        self._persist(packet)

    def corroborate(self, packet_id: str, agent_id: str) -> None:
        """Add a corroborating agent. Upgrades validation_status."""
        if packet_id not in self._index:
            return
        packet = self._index[packet_id]
        if agent_id not in packet.provenance.corroborated_by:
            packet.provenance.corroborated_by.append(agent_id)
        if len(packet.provenance.corroborated_by) >= 2:
            packet.validation_status = ValidationStatus.CORROBORATED
        elif packet.validation_status == ValidationStatus.UNVALIDATED:
            packet.validation_status = ValidationStatus.VALIDATED
        self._persist(packet)

    # ── Retrieval ─────────────────────────────────────────────────

    def retrieve(
        self,
        query_env: dict,
        task_context: str,
        domain: Optional[str] = None,
        task_family: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MINIMUM_SCORE,
        exclude_ids: Optional[list[str]] = None,
    ) -> list[RetrievalResult]:
        """
        Retrieve the most relevant Experience Packets for a query context.

        Args:
            query_env: Dict describing the target environment.
            task_context: Free text description of the current task/problem.
            domain: Optional domain filter (hard filter — cross-domain returns 0).
            task_family: Optional task family hint for boosting.
            top_k: Maximum number of results to return.
            min_score: Minimum score threshold — packets below this are withheld.
            exclude_ids: Packet IDs to exclude (e.g. already tried).

        Returns:
            List of RetrievalResult, sorted by score descending.
        """
        exclude = set(exclude_ids or [])
        results = []

        for pid, packet in self._index.items():
            if pid in exclude:
                continue
            if packet.validation_status == ValidationStatus.DEPRECATED:
                continue

            score = score_packet(
                packet=packet,
                query_env=query_env,
                task_context=task_context,
                domain=domain,
                task_family=task_family,
            )

            if score >= min_score:
                results.append(RetrievalResult(
                    packet=packet,
                    score=score,
                    score_breakdown={},
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ── Introspection ─────────────────────────────────────────────

    def stats(self) -> dict:
        """Summary statistics for the store."""
        packets = list(self._index.values())
        by_domain: dict[str, int] = defaultdict(int)
        by_status: dict[str, int] = defaultdict(int)
        for p in packets:
            by_domain[p.domain] += 1
            by_status[p.validation_status.value] += 1
        return {
            "total_packets": len(packets),
            "by_domain": dict(by_domain),
            "by_status": dict(by_status),
            "avg_trust_score": round(
                sum(p.trust_score for p in packets) / len(packets), 3
            ) if packets else 0.0,
        }

    def get(self, packet_id: str) -> Optional[ExperiencePacket]:
        return self._index.get(packet_id)

    def list_ids(self, domain: Optional[str] = None) -> list[str]:
        if domain:
            return [pid for pid, p in self._index.items() if p.domain == domain]
        return list(self._index.keys())


# ─── Deserialisation helper ──────────────────────────────────────────────────

def _packet_from_dict(data: dict) -> ExperiencePacket:
    """Reconstruct an ExperiencePacket from a stored JSON dict."""
    from datetime import datetime
    from .schema import (
        Scenario, EnvironmentSignature, FailureStructure,
        SolutionPath, SolutionStep, TransferableSkill,
        Outcome, Variant, Provenance, ProvenanceEntry,
    )

    env_data = data["scenario"]["environment_signature"]
    env_known = {
        k: env_data.get(k) for k in
        ["protocol", "flow", "provider", "runtime", "config_surface", "app_type"]
        if env_data.get(k)
    }
    env_custom = {k: v for k, v in env_data.items()
                  if k not in {"protocol", "flow", "provider", "runtime",
                               "config_surface", "app_type"}}

    provenance_data = data.get("provenance", {})
    reuse_log = [
        ProvenanceEntry(
            agent_id=e["agent_id"],
            task_context=e["task_context"],
            outcome=TaskOutcome(e["outcome"]),
            attribution_score=e["attribution_score"],
            timestamp=datetime.fromisoformat(e["timestamp"]),
        )
        for e in provenance_data.get("prior_reuse_log", [])
    ]

    outcome_data = data["outcome"]
    sol_data = data["solution"]

    return ExperiencePacket(
        experience_id=data["experience_id"],
        schema_version=data["schema_version"],
        created_at=datetime.fromisoformat(data["created_at"]),
        source_agent_id=data["source_agent_id"],
        domain=data["domain"],
        task_family=data["task_family"],
        confidence_score=data["confidence_score"],
        validation_status=ValidationStatus(data["validation_status"]),
        reuse_count=data.get("reuse_count", 0),
        trust_score=data.get("trust_score", 0.5),
        scenario=Scenario(
            task_goal=data["scenario"]["task_goal"],
            environment_signature=EnvironmentSignature(**env_known, custom=env_custom),
            observable_symptoms=data["scenario"]["observable_symptoms"],
            tools_available=data["scenario"].get("tools_available", []),
            preconditions=data["scenario"].get("preconditions", []),
        ),
        failure=FailureStructure(
            failure_signature=data["failure"]["failure_signature"],
            confirmed_root_cause=data["failure"]["confirmed_root_cause"],
            misleading_signals=data["failure"].get("misleading_signals", []),
            failed_attempts=data["failure"].get("failed_attempts", []),
        ),
        solution=SolutionPath(
            steps=[
                SolutionStep(
                    step_id=s["step_id"],
                    action=s["action"],
                    tool_used=s.get("tool_used"),
                    rationale=s.get("rationale"),
                    is_adaptation_point=s.get("is_adaptation_point", False),
                )
                for s in sol_data["steps"]
            ],
            why_it_worked=sol_data["why_it_worked"],
            branching_logic=sol_data.get("branching_logic"),
            recovery_path=sol_data.get("recovery_path"),
        ),
        transferable_skill=TransferableSkill(
            skill_statement=data["transferable_skill"]["skill_statement"],
            applicable_when=data["transferable_skill"]["applicable_when"],
            not_applicable_when=data["transferable_skill"]["not_applicable_when"],
            adaptation_required=data["transferable_skill"]["adaptation_required"],
            adaptation_hints=data["transferable_skill"].get("adaptation_hints"),
            prerequisites=data["transferable_skill"].get("prerequisites", []),
        ),
        outcome=Outcome(
            result=TaskOutcome(outcome_data["result"]),
            confidence_after=outcome_data["confidence_after"],
            time_to_resolve=outcome_data.get("time_to_resolve"),
            retry_count=outcome_data.get("retry_count"),
            human_intervention=outcome_data.get("human_intervention", False),
        ),
        variants=[
            Variant(
                variant_id=v["variant_id"],
                environment_signature=EnvironmentSignature(
                    **{k: v["environment_signature"].get(k)
                       for k in ["protocol", "flow", "provider", "runtime",
                                 "config_surface", "app_type"]
                       if v["environment_signature"].get(k)}
                ),
                overrides=v["overrides"],
                notes=v.get("notes"),
            )
            for v in data.get("variants", [])
        ],
        provenance=Provenance(
            evidence_references=provenance_data.get("evidence_references", []),
            corroborated_by=provenance_data.get("corroborated_by", []),
            prior_reuse_log=reuse_log,
            lineage=provenance_data.get("lineage"),
        ),
    )
