# experience.md: A Standard for Transferable Agent Experience

**Version:** 0.1.0-draft  
**Authors:** Quantum Agents Project  
**Status:** Draft for community review  
**Repository:** github.com/quantum-agents/experience-md

---

## Abstract

Current AI agent systems are knowledge-rich but experience-poor. They retrieve documents, recall conversation history, and invoke tools — but they do not transfer *operational maturity* earned through real-world task execution. This paper defines `experience.md`, an open standard for packaging, versioning, retrieving, and adapting agent experience as structured, transferable artifacts. We introduce the Experience Packet as the core unit of the standard, define a schema and lifecycle for experience packets, specify a deterministic adaptation mechanism for cross-environment transfer, and propose a trust and provenance model for experience quality control. A reference Python implementation (`experiencemd`) accompanies this specification.

---

## 1. Introduction

When a skilled human engineer encounters a broken OAuth flow, they do not re-read the RFC. They draw on *experience* — memory of what caused similar failures, which recovery paths worked, which symptoms were misleading. That operational maturity, earned through repeated real-world encounters, is qualitatively different from knowledge retrieved from documentation.

AI agents lack this layer entirely. When an agent fails on a task, it can retrieve documentation, apply in-context reasoning, or recall prior conversation history. What it cannot do is access the distilled, validated lesson from an agent that has *actually solved this class of problem before* — the recovery path, the misleading signals, the adaptation required for a different environment.

This gap is the motivation for `experience.md`.

### 1.1 The Core Claim

We claim that structured, context-aware transferred experience can outperform document retrieval on repeated real-world tasks with high edge-case density — specifically when:

1. The task family recurs with environment-level variation
2. Documentation is insufficient or misleading
3. Prior execution has generated validated recovery paths
4. The transfer target shares sufficient contextual similarity with the transfer source

### 1.2 What This Standard Defines

`experience.md` specifies:

- **The Experience Packet** — the atomic unit of transferable experience
- **The Schema** — structured fields encoding scenario, failure, solution, and transfer metadata
- **The Lifecycle** — how packets are created, validated, versioned, and retired
- **The Retrieval Protocol** — multi-factor similarity scoring for relevant packet discovery
- **The Adaptation Mechanism** — deterministic environment diff + constrained LLM gap-filling
- **The Trust Model** — reputation-based quality control and provenance tracking
- **The Versioning Model** — git-style snapshots enabling reproducible experiments and rollback

---

## 2. Background and Related Work

### 2.1 Current Agent Memory Systems

Agent memory research has produced several distinct approaches:

**Episodic memory** (MemGPT, LangGraph persistence) stores raw interaction history and replays or summarizes it on demand. This preserves detail but does not abstract reusable patterns from specific episodes.

**Retrieval-Augmented Generation (RAG)** retrieves document chunks relevant to a query. This is highly effective for knowledge retrieval but documents contain *descriptions of* procedures, not *evidence of* their effectiveness under specific conditions.

**Shared memory pools** (CrewAI shared memory, AutoGen group chat) allow agents to post notes accessible to other agents. This is useful for coordination but provides no structure, quality filtering, or adaptation mechanism.

**Fine-tuning on interaction data** embeds experience directly into model weights. This is expensive, non-auditable, non-reversible, and cannot be selectively applied.

### 2.2 The Gap

None of these approaches capture the structured artifact of *what happened, why, what worked, and when that pattern applies* in a form that:

- Can be selectively retrieved by contextual similarity
- Can be adapted to a target environment before application
- Carries provenance and trust metadata
- Can be versioned, audited, and rolled back

`experience.md` is designed to fill exactly this gap.

### 2.3 Relationship to Existing Protocols

**MCP (Model Context Protocol)** standardizes tool and data access. `experience.md` operates above MCP — it is concerned with *learned patterns from tool use*, not the tool interfaces themselves.

**A2A (Agent-to-Agent)** defines communication protocols between agents. `experience.md` is the *payload* of what agents usefully exchange — not the transport layer but the content standard.

---

## 3. Core Concepts

### 3.1 The Experience Packet

An Experience Packet is a structured artifact derived from a real agent execution episode. It is not a raw log, a conversation summary, or a documentation chunk. It is a compressed, validated, transferable representation of *what was learned* from a real task.

An Experience Packet has three layers:

**Layer 1 — Scenario** (what was the situation)  
Encodes the task goal, environment signature, tools available, preconditions, and observable symptoms.

**Layer 2 — Solution Path** (what was done)  
Encodes the steps taken, branching decisions, failed attempts, and the recovery path that succeeded.

**Layer 3 — Transferable Skill** (what generalises)  
Encodes the abstracted pattern, its applicability conditions, adaptation requirements, and confidence.

The critical design principle: **Layer 3 is not a summary of Layers 1 and 2. It is a separate abstraction pass** that deliberately removes context-specific detail to preserve the transferable core.

### 3.2 The Quantum Superposition Principle

An experience should not exist as one fixed solution. It should exist as multiple possible interpretations depending on the retrieval context. This is operationalised through *variants* — a single packet can carry multiple environment-specific execution paths that share the same transferable skill at Layer 3.

When retrieved, the correct variant is selected (collapsed) based on the target environment signature. This is the packet-level analogue of quantum state collapse: the experience exists in superposition until a specific retrieval context resolves it to the most applicable form.

### 3.3 Quantumity

Quantumity is the mode in which an agent participates in the shared experience network. When enabled, the agent can:

- Contribute validated Experience Packets from successful task execution
- Retrieve contextually relevant packets from the shared store
- Receive adapted versions fitted to its current environment

Quantumity is opt-in by design. This is a governance decision, not a technical limitation: sharing should be intentional, auditable, and revocable.

---

## 4. The experience.md Schema

All fields use YAML syntax. Required fields are marked `[R]`, optional `[O]`.

```yaml
# ─── PACKET METADATA ─────────────────────────────────────────────
experience_id: [R]        # UUID, globally unique
schema_version: [R]       # e.g. "0.1.0"
created_at: [R]           # ISO 8601 timestamp
source_agent_id: [R]      # Hashed/anonymised agent identifier
domain: [R]               # e.g. "oauth", "browser-automation", "api-integration"
task_family: [R]          # e.g. "redirect-uri-mismatch", "rate-limit-recovery"
confidence_score: [R]     # float 0.0–1.0, computed at pack time
validation_status: [R]    # "unvalidated" | "validated" | "corroborated" | "deprecated"
reuse_count: [O]          # integer, incremented on each successful retrieval use
trust_score: [O]          # float 0.0–1.0, maintained by trust engine

# ─── SCENARIO ────────────────────────────────────────────────────
scenario:
  task_goal: [R]          # Plain language description of what was being attempted
  environment_signature:  # [R] Structured environment descriptor
    protocol: [O]         # e.g. "OIDC", "REST", "GraphQL"
    flow: [O]             # e.g. "auth-code", "client-credentials"
    provider: [O]         # e.g. "azure-ad", "keycloak", "cognito"
    runtime: [O]          # e.g. "node18", "python311", "dotnet8"
    config_surface: [O]   # e.g. "env-file", "k8s-secret", "appsettings"
    app_type: [O]         # e.g. "spa", "server", "mobile"
    custom: [O]           # dict of domain-specific env fields
  tools_available: [O]    # list of tool names accessible during execution
  preconditions: [O]      # list of assumed-true states before execution
  observable_symptoms: [R] # list of observable signals that triggered the episode

# ─── FAILURE STRUCTURE ───────────────────────────────────────────
failure:
  failure_signature: [R]  # Canonical description of the failure class
  misleading_signals: [O] # list of signals that pointed to wrong causes
  failed_attempts: [O]    # list of approaches tried that did not work
  confirmed_root_cause: [R] # The actual cause, confirmed post-resolution

# ─── SOLUTION PATH ───────────────────────────────────────────────
solution:
  steps: [R]              # Ordered list of steps
    - step_id: [R]        # Integer
      action: [R]         # What was done
      tool_used: [O]      # Tool invoked, if any
      rationale: [O]      # Why this step was taken
      is_adaptation_point: [O] # bool — must this be modified for other envs?
  branching_logic: [O]    # Conditions under which different paths were taken
  recovery_path: [O]      # Specific path taken after a failed attempt
  why_it_worked: [R]      # Explanation of the root cause resolution

# ─── TRANSFERABLE SKILL ──────────────────────────────────────────
transferable_skill:
  skill_statement: [R]    # One or two sentence abstracted pattern
  applicable_when: [R]    # list of conditions under which this skill applies
  not_applicable_when: [R] # list of conditions under which it does not apply
  adaptation_required: [R] # list of what must change per environment
  adaptation_hints: [O]   # Free text guidance for adapters
  prerequisites: [O]      # What must be true for this skill to be safely applied

# ─── VARIANTS ────────────────────────────────────────────────────
variants: [O]             # list of environment-specific execution paths
  - variant_id: [R]       # e.g. "azure-ad-v1"
    environment_signature: [R] # Specific env this variant applies to
    overrides: [R]        # dict of solution step modifications for this env
    notes: [O]            # Variant-specific observations

# ─── OUTCOME ─────────────────────────────────────────────────────
outcome:
  result: [R]             # "success" | "partial" | "failure"
  time_to_resolve: [O]    # seconds
  retry_count: [O]        # integer
  human_intervention: [O] # bool
  confidence_after: [R]   # Agent's confidence in solution, 0.0–1.0

# ─── PROVENANCE AND TRUST ────────────────────────────────────────
provenance:
  evidence_references: [O] # list of docs/tools consulted
  corroborated_by: [O]    # list of agent IDs that validated this packet
  prior_reuse_log: [O]    # list of {agent_id, task_context, outcome, attribution_score}
  lineage: [O]            # parent packet ID if derived from another
```

---

## 5. The Experience Lifecycle

An Experience Packet moves through five stages:

```
CAPTURED → STRUCTURED → VALIDATED → PUBLISHED → DEPRECATED
```

**CAPTURED:** Raw episode data is collected immediately after task execution. At this stage the packet is private and unverified.

**STRUCTURED:** The abstraction pass runs — Layer 3 (transferable skill) is extracted. Quality checks are applied: confidence threshold, required field completeness, privacy scrubbing.

**VALIDATED:** The packet has been tested in at least one retrieval scenario. For `corroborated` status, two independent agents from different lineages must confirm the skill transferred successfully.

**PUBLISHED:** The packet enters the shared Quantum Experience Mesh and is available for retrieval.

**DEPRECATED:** The packet has failed transfer attempts, been superseded by a higher-confidence version, or its environmental context is no longer relevant.

---

## 6. Retrieval Protocol

Retrieval uses a multi-factor scoring function. Given a query context Q and a candidate packet P, the retrieval score S is:

```
S(P, Q) = w1 × task_family_sim(P, Q)
        + w2 × failure_sig_sim(P, Q)
        + w3 × env_sig_sim(P, Q)
        + w4 × tool_sim(P, Q)
        + w5 × trust_score(P)
        + w6 × recency(P)
```

**Default weights:**

| Factor | Weight | Rationale |
|---|---|---|
| Task family similarity | 0.30 | Primary intent signal |
| Failure signature similarity | 0.25 | Most discriminating feature |
| Environment similarity | 0.20 | Determines adaptation cost |
| Tool similarity | 0.10 | Affects step portability |
| Trust score | 0.10 | Quality filter |
| Recency | 0.05 | Freshness signal |

Similarity functions use cosine similarity over embedding vectors for semantic fields, and Jaccard similarity over structured fields (tool lists, environment signature keys).

The top-K packets are returned (default K=5), subject to a minimum score threshold (default 0.45). Packets below the threshold are withheld even if they are top-ranked.

---

## 7. Adaptation Mechanism

Adaptation converts a retrieved packet from its source environment to the target environment. It has two stages.

### 7.1 Stage 1 — Deterministic Diff

The environment signature diff engine compares source and target environments field by field and produces a substitution map.

```python
source_env = {"provider": "azure-ad", "config_surface": "env-file", "app_type": "spa"}
target_env = {"provider": "keycloak", "config_surface": "k8s-secret", "app_type": "server"}

diff → {
    "provider": ("azure-ad", "keycloak"),
    "config_surface": ("env-file", "k8s-secret"),
    "app_type": ("spa", "server")
}
```

For each diff pair, the adapter applies a known mapping table (maintained and versioned separately from packets). For example:

```
("azure-ad", "keycloak") → {
    "Azure App Registration console" → "Keycloak Admin → Clients → {client_id}",
    "AZURE_CLIENT_ID" → "KEYCLOAK_CLIENT_ID",
    "Application ID" → "Client ID"
}
```

Steps flagged with `is_adaptation_point: true` are processed through the mapping table. Steps without that flag are carried forward unchanged.

### 7.2 Stage 2 — Constrained LLM Gap-Fill

Where the mapping table has no entry for a diff pair, a constrained LLM call fills the gap. The prompt is tightly structured:

```
Given:
- Source step: {step_action}
- Source environment: {source_env}
- Target environment: {target_env}
- Known substitutions already applied: {applied_mappings}

Produce the adapted version of this step for the target environment.
Do not introduce new steps. Do not speculate beyond the substitution.
If uncertain, flag the step with needs_human_review: true.
```

This ensures the LLM operates within a bounded substitution task, not a free-form generation task. Estimated ratio: approximately 70% of adaptation is handled deterministically; 30% falls to the LLM.

---

## 8. Trust and Provenance Model

### 8.1 Trust Score

Every packet carries a trust score computed as:

```
trust_score = base_confidence
            × reuse_success_rate
            × corroboration_weight
            × recency_decay
```

Where:
- `base_confidence` is set at pack time (agent's self-assessed confidence, 0.0–1.0)
- `reuse_success_rate` is updated on each retrieval: successful use increases, failed use decreases
- `corroboration_weight` is 1.0 for unvalidated, 1.2 for validated, 1.5 for corroborated
- `recency_decay` applies domain-specific half-lives (technical patterns decay slowly, market/social patterns decay fast)

### 8.2 Transfer Provenance Log

Every retrieval and application of a packet is logged with:

```yaml
transfer_log_entry:
  packet_id: exp_oauth_001_v3
  retrieving_agent_id: agent_b_hashed
  task_context: "keycloak redirect failure in staging"
  steps_in_packet: 5
  steps_executed: 4
  steps_modified: 1
  steps_skipped: 1
  outcome: "success"
  base_success_rate_on_similar: 0.35   # counterfactual estimate
  raw_attribution: 0.82
  true_attribution: 0.82 × (1 - 0.35) = 0.533
```

**True attribution** corrects for tasks that would have been solvable without the transferred experience. This prevents false positives in evaluation.

### 8.3 Attribution Score Formula

```
raw_attribution = (steps_executed / steps_total)
                × outcome_weight    # 1.0 success, 0.5 partial, 0.0 failure
                × relevance_score   # retrieval similarity score

true_attribution = raw_attribution × (1 - base_success_rate_on_similar_tasks)
```

---

## 9. Versioning Model

### 9.1 Packet Versioning

Individual packets are versioned using semantic versioning:

- **PATCH** (x.x.1): Minor corrections, additional notes, trust score updates
- **MINOR** (x.1.0): New variant added, adaptation hints extended
- **MAJOR** (1.0.0): Core pattern changed, applicability conditions revised

All versions are retained. Retrieval defaults to the latest stable version but can be pinned to any prior version.

### 9.2 Baseline Versioning

Baselines snapshot the entire state of the experience store at a point in time:

```yaml
baseline_v2:
  created_at: "2025-04-01T00:00:00Z"
  packets_included: [exp_oauth_001_v3, exp_oauth_002_v1, ...]
  model_config: {model: "claude-sonnet-4", temperature: 0.2}
  task_set_hash: "sha256:abc123..."
  notes: "Post-ablation refinement, adaptation weights tuned"
```

Baselines are immutable once created. Experiments always compare against a named, pinned baseline.

### 9.3 Mapping Table Versioning

The adaptation mapping tables are versioned independently:

```
mapping_tables/
  oauth_provider_mappings_v1.yaml
  oauth_provider_mappings_v2.yaml   ← added Cognito entries
  config_surface_mappings_v1.yaml
```

Packets record which mapping table version was used at pack time, enabling exact reproduction of prior adaptation runs.

---

## 10. Experiment Design for Validation

To validate the core claim of `experience.md`, we propose the following controlled experiment.

### 10.1 Hypothesis

H1: Quantumity-based experience transfer (structured packets + adaptation) outperforms RAG and shared memory on repeated real-world agent tasks with environment variation.

### 10.2 Four Comparison Modes

| Mode | Context Provided |
|---|---|
| Base | No additional context |
| RAG | Official documentation chunks |
| Shared Memory | Raw prior agent logs |
| Quantumity | Structured, adapted Experience Packets |

### 10.3 Task Families

Initial domain: OAuth/API integration troubleshooting

Task families: redirect-uri-mismatch, token-refresh-failure, scope-permission-error

Similarity tiers: Near-transfer (Tier 1), Moderate-transfer (Tier 2), Far-transfer (Tier 3)

Each task run 3 times with majority vote to control for LLM sampling variance.

### 10.4 Success Threshold

Strong signal: Quantumity achieves ≥15% higher success rate than RAG, or ≥25% reduction in retries, with true attribution score ≥0.4 on majority of successful transfers.

---

## 11. Conclusion

`experience.md` proposes a new layer in the agent stack: a structured, versioned, transferable representation of operational experience earned through real-world task execution. By separating experience into three layers (scenario, solution path, transferable skill), defining a deterministic adaptation mechanism, and grounding quality control in provenance tracking and counterfactual attribution, we create a standard that is auditable, reproducible, and empirically testable.

The reference Python implementation (`experiencemd`) provides a working basis for community adoption and experimentation. We invite developers, researchers, and agent system builders to contribute to the schema, extend the mapping tables, and run controlled experiments using the proposed evaluation framework.

The standard is deliberately minimal in its first version. Every field that is present must earn its place through demonstrated utility in real retrieval and adaptation scenarios. We expect the schema to evolve substantially through community use.

---

## Appendix A — Full Example Packet

```yaml
experience_id: "exp-oauth-001"
schema_version: "0.1.0"
created_at: "2026-03-29T10:00:00Z"
source_agent_id: "agent-a9f3b2"
domain: "oauth"
task_family: "redirect-uri-mismatch"
confidence_score: 0.91
validation_status: "corroborated"
reuse_count: 7
trust_score: 0.87

scenario:
  task_goal: "Fix OAuth login failure — users authenticated but callback rejected"
  environment_signature:
    protocol: "OIDC"
    flow: "auth-code"
    provider: "azure-ad"
    config_surface: "env-file"
    app_type: "spa"
  observable_symptoms:
    - "Token generation succeeds"
    - "Callback URL returns 401 or redirect loop"
    - "No error in auth provider logs"

failure:
  failure_signature: "callback_uri_rejected_post_auth"
  misleading_signals:
    - "Token generation appeared successful"
    - "Auth provider showed no errors"
  failed_attempts:
    - "Checked token scopes — correct"
    - "Verified client ID — correct"
  confirmed_root_cause: "Redirect URI mismatch between app registration and runtime config"

solution:
  steps:
    - step_id: 1
      action: "Retrieve exact callback URL from runtime config"
      is_adaptation_point: false
    - step_id: 2
      action: "Open Azure App Registration → Authentication → Redirect URIs"
      is_adaptation_point: true
    - step_id: 3
      action: "Compare character-by-character: scheme, host, path, trailing slash"
      is_adaptation_point: false
    - step_id: 4
      action: "Update env-file AZURE_REDIRECT_URI to exactly match registration"
      is_adaptation_point: true
    - step_id: 5
      action: "Re-test auth flow end-to-end"
      is_adaptation_point: false
  why_it_worked: "Exact URI equality required by OIDC spec — even trailing slash differences cause rejection"

transferable_skill:
  skill_statement: >
    When auth partially succeeds but callback is rejected, verify exact redirect URI
    equality (scheme, host, path, trailing slash) between provider registration and
    runtime configuration. These are independent surfaces that must match exactly.
  applicable_when:
    - "OIDC or OAuth2 auth-code flow"
    - "Callback-based authentication"
    - "Auth appears to succeed but callback fails"
  not_applicable_when:
    - "Client credentials flow (no callback)"
    - "Token scope or audience errors"
    - "Provider-side rejections before token issuance"
  adaptation_required:
    - "Provider-specific registration console path"
    - "Environment-specific config surface and variable names"
  prerequisites:
    - "Access to provider admin console"
    - "Access to runtime configuration"

variants:
  - variant_id: "azure-ad-v1"
    environment_signature: {provider: "azure-ad", config_surface: "env-file"}
    overrides:
      step_2: "Open Azure Portal → App Registrations → {app_name} → Authentication"
      step_4: "Update AZURE_REDIRECT_URI in .env file"
  - variant_id: "keycloak-v1"
    environment_signature: {provider: "keycloak", config_surface: "k8s-secret"}
    overrides:
      step_2: "Open Keycloak Admin → Clients → {client_id} → Settings → Valid Redirect URIs"
      step_4: "Update KEYCLOAK_REDIRECT_URI in Kubernetes secret and restart pod"

outcome:
  result: "success"
  time_to_resolve: 840
  retry_count: 2
  human_intervention: false
  confidence_after: 0.94

provenance:
  corroborated_by: ["agent-b7c1a3", "agent-d2e8f1"]
  prior_reuse_log:
    - {task_context: "Keycloak SPA callback", outcome: "success", attribution_score: 0.71}
    - {task_context: "Cognito redirect loop", outcome: "success", attribution_score: 0.64}
```

---

## Appendix B — Versioning Glossary

| Term | Definition |
|---|---|
| Experience Packet | Atomic unit of transferable experience |
| Environment Signature | Structured descriptor of execution environment |
| Adaptation Point | Step requiring environment-specific modification |
| Transferable Skill | Layer 3 abstraction, invariant across environment variants |
| Quantumity | Opt-in mode enabling shared experience participation |
| Baseline | Immutable snapshot of store state for experiment reproducibility |
| True Attribution | Attribution score corrected for counterfactual base success rate |
| Trust Score | Composite quality signal for a packet, updated through reuse |
