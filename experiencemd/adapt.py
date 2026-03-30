"""
experience.adapt — adapt an Experience Packet to a target environment.

Two-stage mechanism:
  Stage 1: Deterministic diff — environment signature comparison + mapping tables
  Stage 2: Constrained LLM gap-fill — only for unmapped substitutions

Usage:
    from experiencemd import ExperienceAdapter

    adapter = ExperienceAdapter()
    result = adapter.adapt(packet, target_env={"provider": "keycloak", ...})

    print(result.adapted_steps)
    print(result.unmapped_fields)   # Fields that need manual review
    print(result.confidence)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .schema import EnvironmentSignature, ExperiencePacket, SolutionStep, Variant


# ─── Built-in mapping tables ────────────────────────────────────────────────
# These are the deterministic substitution tables.
# Each entry: (source_value, target_value) -> {text_to_find: replacement}
# Extend by loading external YAML/JSON mapping files.

BUILTIN_MAPPINGS: dict[str, dict[tuple[str, str], dict[str, str]]] = {

    "provider": {
        ("azure-ad", "keycloak"): {
            "Azure App Registration": "Keycloak Admin → Clients → {client_id}",
            "Azure Portal": "Keycloak Admin Console",
            "AZURE_CLIENT_ID": "KEYCLOAK_CLIENT_ID",
            "AZURE_CLIENT_SECRET": "KEYCLOAK_CLIENT_SECRET",
            "AZURE_REDIRECT_URI": "KEYCLOAK_REDIRECT_URI",
            "Application ID": "Client ID",
            "Tenant ID": "Realm",
            "app registration": "Keycloak client",
        },
        ("azure-ad", "cognito"): {
            "Azure App Registration": "AWS Cognito → User Pools → App Clients",
            "Azure Portal": "AWS Console",
            "AZURE_CLIENT_ID": "COGNITO_CLIENT_ID",
            "AZURE_CLIENT_SECRET": "COGNITO_CLIENT_SECRET",
            "AZURE_REDIRECT_URI": "COGNITO_REDIRECT_URI",
            "Application ID": "App Client ID",
            "Tenant ID": "User Pool ID",
        },
        ("keycloak", "azure-ad"): {
            "Keycloak Admin → Clients": "Azure App Registrations",
            "Keycloak Admin Console": "Azure Portal",
            "KEYCLOAK_CLIENT_ID": "AZURE_CLIENT_ID",
            "KEYCLOAK_CLIENT_SECRET": "AZURE_CLIENT_SECRET",
            "KEYCLOAK_REDIRECT_URI": "AZURE_REDIRECT_URI",
            "Client ID": "Application ID",
            "Realm": "Tenant ID",
        },
        ("cognito", "keycloak"): {
            "AWS Cognito": "Keycloak",
            "User Pool": "Realm",
            "App Client": "Keycloak Client",
            "COGNITO_CLIENT_ID": "KEYCLOAK_CLIENT_ID",
            "COGNITO_REDIRECT_URI": "KEYCLOAK_REDIRECT_URI",
        },
    },

    "config_surface": {
        ("env-file", "k8s-secret"): {
            ".env file": "Kubernetes Secret",
            "env file": "k8s secret",
            "update the .env": "update the k8s secret and restart pod",
            "REDIRECT_URI=": "REDIRECT_URI: (in secret YAML)",
        },
        ("env-file", "appsettings"): {
            ".env file": "appsettings.json",
            "env file": "appsettings",
            "update the .env": "update appsettings.json",
        },
        ("k8s-secret", "env-file"): {
            "Kubernetes Secret": ".env file",
            "k8s secret": "env file",
            "restart pod": "restart the dev server",
        },
    },

    "app_type": {
        ("spa", "server"): {
            "SPA": "server-side app",
            "browser-based": "server-side",
            "Public client": "Confidential client",
        },
        ("server", "spa"): {
            "server-side": "browser-based SPA",
            "Confidential client": "Public client",
        },
    },
}


# ─── Diff engine ────────────────────────────────────────────────────────────

@dataclass
class EnvDiff:
    """Result of comparing two environment signatures."""
    changed_fields: dict[str, tuple[str, str]]   # field → (source_val, target_val)
    unchanged_fields: dict[str, str]             # field → value (same in both)
    added_fields: dict[str, str]                 # field in target only
    removed_fields: dict[str, str]               # field in source only

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_fields or self.added_fields or self.removed_fields)


def diff_environments(
    source: EnvironmentSignature,
    target: dict[str, Any],
) -> EnvDiff:
    """Compute field-by-field diff between source and target environments."""
    source_dict = source.to_dict()
    changed, unchanged, added, removed = {}, {}, {}, {}

    for key, src_val in source_dict.items():
        if key in target:
            if str(src_val) != str(target[key]):
                changed[key] = (str(src_val), str(target[key]))
            else:
                unchanged[key] = str(src_val)
        else:
            removed[key] = str(src_val)

    for key, tgt_val in target.items():
        if key not in source_dict:
            added[key] = str(tgt_val)

    return EnvDiff(
        changed_fields=changed,
        unchanged_fields=unchanged,
        added_fields=added,
        removed_fields=removed,
    )


def build_substitution_map(
    diff: EnvDiff,
    extra_mappings: Optional[dict] = None,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """
    Build a text substitution map from an EnvDiff.

    Returns:
        substitutions: {find_text: replace_text}
        unmapped_changes: list of (field, change_description) where no mapping exists
    """
    substitutions: dict[str, str] = {}
    unmapped: list[tuple[str, str]] = []

    all_mappings = {**BUILTIN_MAPPINGS}
    if extra_mappings:
        for field_name, mappings in extra_mappings.items():
            if field_name in all_mappings:
                all_mappings[field_name].update(mappings)
            else:
                all_mappings[field_name] = mappings

    for field_name, (src_val, tgt_val) in diff.changed_fields.items():
        field_table = all_mappings.get(field_name, {})
        key = (src_val, tgt_val)
        reverse_key = (tgt_val, src_val)

        if key in field_table:
            substitutions.update(field_table[key])
        elif reverse_key in field_table:
            # Auto-derive reverse substitution
            reverse_subs = {v: k for k, v in field_table[reverse_key].items()}
            substitutions.update(reverse_subs)
        else:
            unmapped.append((field_name, f"{src_val} → {tgt_val}"))

    return substitutions, unmapped


def apply_substitutions(text: str, substitutions: dict[str, str]) -> str:
    """Apply substitution map to a text string. Longer matches take priority."""
    for find, replace in sorted(substitutions.items(), key=lambda x: -len(x[0])):
        text = text.replace(find, replace)
    return text


# ─── Adaptation result ───────────────────────────────────────────────────────

@dataclass
class AdaptationResult:
    """Result of adapting a packet to a target environment."""
    source_packet_id: str
    target_env: dict
    adapted_steps: list[dict]            # Step dicts with adapted action text
    adapted_skill_statement: str
    adapted_hints: str
    substitutions_applied: dict[str, str]
    unmapped_fields: list[tuple[str, str]]  # Fields needing manual/LLM attention
    variant_used: Optional[str]           # If a pre-built variant was matched
    confidence: float                     # 0.0–1.0, lower if many unmapped fields
    needs_review: list[int]               # step_ids that need human review

    def summary(self) -> str:
        lines = [
            f"Adaptation of {self.source_packet_id[:8]}...",
            f"  Substitutions applied: {len(self.substitutions_applied)}",
            f"  Unmapped fields: {len(self.unmapped_fields)}",
            f"  Steps needing review: {self.needs_review}",
            f"  Confidence: {self.confidence:.2f}",
        ]
        if self.variant_used:
            lines.append(f"  Variant used: {self.variant_used}")
        return "\n".join(lines)

    def adapted_steps_text(self) -> list[str]:
        return [s["action"] for s in self.adapted_steps]


# ─── Adapter ─────────────────────────────────────────────────────────────────

class ExperienceAdapter:
    """
    Adapts Experience Packets to target environments.

    Stage 1: Deterministic diff + mapping tables (~70% of adaptation).
    Stage 2: Flags unmapped fields for LLM or human review (~30%).

    To enable LLM-based gap-filling, subclass and override `_llm_fill_gaps`.
    """

    def __init__(self, extra_mappings: Optional[dict] = None):
        self.extra_mappings = extra_mappings or {}

    def adapt(
        self,
        packet: ExperiencePacket,
        target_env: dict[str, Any],
    ) -> AdaptationResult:
        """
        Adapt a packet to a target environment.

        1. Check if a pre-built variant matches target_env exactly → use it
        2. Otherwise, run deterministic diff + substitution
        3. Flag unmapped fields for review
        4. Compute adaptation confidence

        Args:
            packet: Source ExperiencePacket.
            target_env: Dict describing the target environment.

        Returns:
            AdaptationResult with adapted steps and metadata.
        """
        # Stage 0: Check for matching pre-built variant
        matched_variant = self._match_variant(packet, target_env)
        if matched_variant:
            return self._adapt_from_variant(packet, matched_variant, target_env)

        # Stage 1: Diff environments
        diff = diff_environments(packet.scenario.environment_signature, target_env)
        substitutions, unmapped = build_substitution_map(diff, self.extra_mappings)

        # Stage 2: Apply substitutions to adaptation-point steps only
        adapted_steps = []
        needs_review = []

        for step in packet.solution.steps:
            adapted_action = step.action
            if step.is_adaptation_point:
                adapted_action = apply_substitutions(step.action, substitutions)
                # Flag if any unmapped fields might affect this step
                for field_name, _ in unmapped:
                    if any(field_name.lower() in word.lower()
                           for word in step.action.split()):
                        needs_review.append(step.step_id)
                        break

            adapted_steps.append({
                "step_id": step.step_id,
                "action": adapted_action,
                "original_action": step.action,
                "was_adapted": step.is_adaptation_point,
                "needs_review": step.step_id in needs_review,
                "tool_used": step.tool_used,
                "rationale": step.rationale,
            })

        # Adapt skill statement and hints
        adapted_skill = apply_substitutions(
            packet.transferable_skill.skill_statement, substitutions
        )
        adapted_hints = apply_substitutions(
            packet.transferable_skill.adaptation_hints or
            "Verify all environment-specific paths and variable names.",
            substitutions,
        )

        # Compute confidence
        confidence = self._compute_adaptation_confidence(
            packet=packet,
            unmapped_count=len(unmapped),
            needs_review_count=len(needs_review),
            diff=diff,
        )

        result = AdaptationResult(
            source_packet_id=packet.experience_id,
            target_env=target_env,
            adapted_steps=adapted_steps,
            adapted_skill_statement=adapted_skill,
            adapted_hints=adapted_hints,
            substitutions_applied=substitutions,
            unmapped_fields=unmapped,
            variant_used=None,
            confidence=confidence,
            needs_review=needs_review,
        )

        # Stage 2: LLM gap-fill for unmapped fields (override to enable)
        if unmapped:
            result = self._llm_fill_gaps(result, packet, unmapped)

        return result

    def _match_variant(
        self,
        packet: ExperiencePacket,
        target_env: dict,
    ) -> Optional[Variant]:
        """Return the best-matching pre-built variant, or None."""
        for variant in packet.variants:
            variant_dict = variant.environment_signature.to_dict()
            match_score = sum(
                1 for k, v in variant_dict.items()
                if str(target_env.get(k, "")) == str(v)
            )
            if match_score == len(variant_dict) and match_score > 0:
                return variant
        return None

    def _adapt_from_variant(
        self,
        packet: ExperiencePacket,
        variant: Variant,
        target_env: dict,
    ) -> AdaptationResult:
        """Use a pre-built variant to build the adaptation result."""
        adapted_steps = []
        for step in packet.solution.steps:
            override_key = f"step_{step.step_id}"
            action = variant.overrides.get(override_key, step.action)
            adapted_steps.append({
                "step_id": step.step_id,
                "action": action,
                "original_action": step.action,
                "was_adapted": override_key in variant.overrides,
                "needs_review": False,
                "tool_used": step.tool_used,
                "rationale": step.rationale,
            })

        return AdaptationResult(
            source_packet_id=packet.experience_id,
            target_env=target_env,
            adapted_steps=adapted_steps,
            adapted_skill_statement=packet.transferable_skill.skill_statement,
            adapted_hints=packet.transferable_skill.adaptation_hints or "",
            substitutions_applied={},
            unmapped_fields=[],
            variant_used=variant.variant_id,
            confidence=min(1.0, packet.trust_score + 0.1),
            needs_review=[],
        )

    def _compute_adaptation_confidence(
        self,
        packet: ExperiencePacket,
        unmapped_count: int,
        needs_review_count: int,
        diff: EnvDiff,
    ) -> float:
        """
        Compute confidence in the adaptation.

        Decreases with:
        - More unmapped fields
        - More steps needing review
        - Large environment diff
        """
        base = packet.trust_score
        unmapped_penalty = min(0.40, unmapped_count * 0.10)
        review_penalty = min(0.20, needs_review_count * 0.05)
        diff_size = len(diff.changed_fields) + len(diff.added_fields)
        diff_penalty = min(0.15, diff_size * 0.03)

        return round(max(0.0, base - unmapped_penalty - review_penalty - diff_penalty), 3)

    def _llm_fill_gaps(
        self,
        result: AdaptationResult,
        packet: ExperiencePacket,
        unmapped: list[tuple[str, str]],
    ) -> AdaptationResult:
        """
        Override in a subclass to add LLM-based gap-filling.

        Default behaviour: return result unchanged with needs_review flags intact.

        Example subclass:
            class LLMAdapter(ExperienceAdapter):
                def _llm_fill_gaps(self, result, packet, unmapped):
                    # Call your LLM here with the structured prompt
                    prompt = self._build_gap_fill_prompt(result, packet, unmapped)
                    # llm_response = call_llm(prompt)
                    # Apply LLM suggestions to result.adapted_steps
                    return result
        """
        return result

    def build_llm_prompt(
        self,
        result: AdaptationResult,
        packet: ExperiencePacket,
        unmapped: list[tuple[str, str]],
    ) -> str:
        """
        Build a structured prompt for LLM gap-filling.
        Call this from your _llm_fill_gaps override.
        """
        steps_needing_review = [
            s for s in result.adapted_steps if s["needs_review"]
        ]
        unmapped_desc = "\n".join(f"  - {f}: {c}" for f, c in unmapped)
        steps_desc = "\n".join(
            f"  Step {s['step_id']}: {s['action']}"
            for s in steps_needing_review
        )

        return f"""You are adapting an agent experience packet to a new environment.

ORIGINAL SKILL:
{packet.transferable_skill.skill_statement}

ENVIRONMENT CHANGE (unmapped fields — these need your attention):
{unmapped_desc}

STEPS NEEDING ADAPTATION:
{steps_desc}

ALREADY APPLIED SUBSTITUTIONS:
{json.dumps(result.substitutions_applied, indent=2)}

TASK:
For each step listed above, produce the adapted version for the target environment.
Rules:
- Do NOT introduce new steps
- Do NOT speculate beyond the substitution needed
- If genuinely uncertain, add "needs_human_review: true" to that step
- Keep adaptations minimal and specific

Respond ONLY with a JSON list:
[
  {{"step_id": 1, "adapted_action": "...", "needs_human_review": false}},
  ...
]"""
