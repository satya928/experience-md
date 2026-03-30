# experiencemd

**Python reference implementation of the `experience.md` standard.**

`experience.md` is an open standard for packaging, storing, retrieving, and adapting AI agent operational experience as structured, transferable artifacts.

> "Knowledge is taught. Skill is earned."
>
> LLMs have knowledge. RAG retrieves knowledge. `experience.md` transfers *earned experience* from real-world task execution — recovery paths, failure signatures, validated skills — in a form agents can retrieve, adapt, and apply.

---

## The core idea

When Agent A fixes a broken OAuth redirect URI in Azure AD, it doesn't just succeed — it *learns* something. That learning is currently lost. Next time a different agent hits the same problem class in Keycloak, it starts from zero.

`experience.md` captures what Agent A learned as a structured **Experience Packet**, stores it, and makes it retrievable and *adaptable* for Agent B — even when the environment is different.

```
Agent A (Azure AD)          Quantum Experience Mesh          Agent B (Keycloak)
       │                            │                               │
  Task succeeds              ◄─── stores ───                       │
  pack.from_episode()              │                               │
       │                           │                   Task starts │
       └──► ExperiencePacket ──────┤                               │
                                   │ ◄── retrieve ────────────────►│
                                   │                    adapt()    │
                                   │                               │
                                   │    "Open Keycloak Admin →     │
                                   │     Clients → Redirect URIs"  │
                                   │    (was: Azure App Reg)       │
```

---

## How it relates to skills.md

If you've used `skills.md` files to give agents structured instructions before a task, `experience.md` is the natural complement:

```
skills.md      = instructions written before execution  →  tells an agent HOW to act
experience.md  = artifacts generated after execution    →  captures what actually worked
```

They form a complete agent learning loop. `skills.md` defines the procedure. `experience.md` records what happened in the real world and what generalised across environments. **You are not choosing between them — you need both.**

---

## Works with any LLM

No model changes, no fine-tuning, no special infrastructure required. `experience.md` sits above the model layer — it structures what gets passed into context, not how the model works. Drop it into any agent built on OpenAI, Anthropic, Gemini, local models, or any framework (LangChain, LangGraph, CrewAI, AutoGen).

---

## Version control for agent experience

`experience.md` brings the same discipline Git brought to code — applied to agent learning:

```
skills versioned     →  revert an agent to any prior skill state
baselines pinned     →  reproducible experiments, comparable results
provenance tracked   →  every packet traces back to its source execution
trust scored         →  reputation updates with every use, like commit history
```

Enterprises running critical agent workflows can audit exactly what an agent knew, when it knew it, and where that knowledge came from.

---

## 30-second demo

```bash
git clone https://github.com/quantum-agents/experience-md
cd experience-md
python examples/oauth_example.py
```

Expected output:
```
[1] Packing Azure AD experience...
  Packed: ExperiencePacket(domain=oauth, family=redirect-uri-mismatch, trust=0.50)

[2] Saving to store...
  Store stats: {'total_packets': 1, 'by_domain': {'oauth': 1}}

[3] Retrieving for Keycloak redirect problem...
  Found 1 result — score: 0.528

[4] Adapting to Keycloak + k8s-secret environment...
  Substitutions applied: 15
  Step 2: Open Keycloak Admin → Clients → {client_id} → Redirect URIs  [adapted]
  Step 4: Update k8s secret KEYCLOAK_REDIRECT_URI to match exactly      [adapted]
  Confidence: 0.41

[5] Trust updated: 0.50 → 0.926 after successful transfer
[6] Validation status: corroborated
```

---

## Install

```bash
pip install experiencemd       # PyPI (coming soon)

# or from source:
git clone https://github.com/quantum-agents/experience-md
cd experience-md
pip install -e .
```

**No dependencies beyond the Python standard library** for the core library. Optional: `pyyaml` for YAML I/O, `numpy`/`sentence-transformers` for embedding-based retrieval (drop-in replacements for the default token similarity).

---

## Quick start

### 1. Pack — create an Experience Packet from a real execution

```python
from experiencemd import pack

packet = pack.from_episode(
    agent_id="my-agent-prod",
    domain="oauth",
    task_family="redirect-uri-mismatch",

    task_goal="Fix OAuth login — users authenticated but callback rejected",
    environment={
        "protocol": "OIDC",
        "flow": "auth-code",
        "provider": "azure-ad",
        "config_surface": "env-file",
        "app_type": "spa",
    },
    observable_symptoms=[
        "Token generation succeeds",
        "Callback URL returns 401 or redirect loop",
    ],

    failure_signature="callback_uri_rejected_post_auth",
    confirmed_root_cause="Redirect URI mismatch between app registration and runtime config",
    misleading_signals=["Token generation appeared successful"],
    failed_attempts=["Checked token scopes", "Verified client ID"],

    steps=[
        {"action": "Retrieve exact callback URL from runtime config",
         "is_adaptation_point": False},
        {"action": "Open Azure App Registration → Authentication → Redirect URIs",
         "is_adaptation_point": True},           # ← will be adapted per environment
        {"action": "Compare URIs character-by-character including trailing slash",
         "is_adaptation_point": False},
        {"action": "Update env-file AZURE_REDIRECT_URI to match registration exactly",
         "is_adaptation_point": True},
        {"action": "Re-test auth flow end-to-end", "is_adaptation_point": False},
    ],
    why_it_worked="OIDC requires exact URI equality — even trailing slash differences cause rejection",

    skill_statement=(
        "When auth partially succeeds but callback fails, verify exact redirect URI "
        "equality (scheme, host, path, trailing slash) between provider registration "
        "and runtime config. These are independent surfaces that must match exactly."
    ),
    applicable_when=["OIDC/OAuth2 auth-code flow", "Callback-based auth"],
    not_applicable_when=["Client credentials flow", "Token scope errors"],
    adaptation_required=[
        "Provider-specific registration console path",
        "Environment config surface and variable names",
    ],

    outcome="success",
    time_to_resolve=840,
    retry_count=2,
)

print(packet)
# ExperiencePacket(id=4f224b48..., domain=oauth, family=redirect-uri-mismatch,
#                  status=unvalidated, trust=0.50)
```

**PII scrubbing is on by default.** Emails, IPs, UUIDs, secrets, and URLs are redacted before the packet is stored. Agent IDs are one-way hashed.

### 2. Store — save and persist packets

```python
from experiencemd import ExperienceStore

store = ExperienceStore("./experience_db")
store.save(packet)

print(store.stats())
# {'total_packets': 1, 'by_domain': {'oauth': 1},
#  'by_status': {'unvalidated': 1}, 'avg_trust_score': 0.5}
```

### 3. Retrieve — find relevant packets for a new task

```python
results = store.retrieve(
    query_env={
        "protocol": "OIDC",
        "flow": "auth-code",
        "provider": "keycloak",       # different provider
        "config_surface": "k8s-secret",
        "app_type": "server",
    },
    task_context="keycloak redirect uri rejected after login oauth callback",
    domain="oauth",
    task_family="redirect-uri-mismatch",   # problem classification
    top_k=5,
)

print(results[0])
# RetrievalResult(score=0.528, packet=4f224b48..., family=redirect-uri-mismatch)
```

Retrieval uses a **multi-factor scoring function** across task family, failure signature, environment similarity, tool overlap, trust score, and recency. All weights are configurable.

### 4. Adapt — translate the packet to the target environment

```python
from experiencemd import ExperienceAdapter

adapter = ExperienceAdapter()
adapted = adapter.adapt(
    results[0].packet,
    target_env={"provider": "keycloak", "config_surface": "k8s-secret"},
)

print(adapted.summary())
# Adaptation of 4f224b48...
#   Substitutions applied: 15
#   Unmapped fields: 0
#   Steps needing review: []
#   Confidence: 0.41

for step in adapted.adapted_steps:
    print(f"  {step['step_id']}. {step['action']}")
# 1. Retrieve exact callback URL from runtime config
# 2. Open Keycloak Admin → Clients → {client_id} → Authentication → Redirect URIs [adapted]
# 3. Compare URIs character-by-character: scheme, host, path, trailing slash
# 4. Update k8s secret KEYCLOAK_REDIRECT_URI to match registration exactly [adapted]
# 5. Re-test auth flow end-to-end
```

Adaptation is **70% deterministic** (mapping tables) + **30% LLM gap-fill** (subclass `ExperienceAdapter._llm_fill_gaps` to enable).

### 5. Trust — update packet quality after use

```python
store.update_trust(
    packet_id=results[0].packet.experience_id,
    transfer_succeeded=True,
    attribution_score=0.75,
    retrieving_agent_id="agent-consumer-b",
    task_context="keycloak redirect failure in staging",
)
# Trust score rises: 0.50 → 0.926
```

### 6. Corroborate — validate with independent agents

```python
store.corroborate(packet_id, "agent-validator-001")
store.corroborate(packet_id, "agent-validator-002")

packet = store.get(packet_id)
print(packet.validation_status)
# ValidationStatus.CORROBORATED  (requires 2+ independent agents)
```

---

## Enabling LLM-based gap-filling

Subclass `ExperienceAdapter` and override `_llm_fill_gaps`:

```python
from experiencemd import ExperienceAdapter

class LLMAdapter(ExperienceAdapter):
    def __init__(self, llm_client, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm_client

    def _llm_fill_gaps(self, result, packet, unmapped):
        if not unmapped:
            return result

        prompt = self.build_llm_prompt(result, packet, unmapped)
        response = self.llm.complete(prompt)   # your LLM call here

        import json
        try:
            suggestions = json.loads(response)
            step_map = {s["step_id"]: s for s in suggestions}
            for step in result.adapted_steps:
                if step["step_id"] in step_map:
                    suggestion = step_map[step["step_id"]]
                    step["action"] = suggestion["adapted_action"]
                    step["needs_review"] = suggestion.get("needs_human_review", False)
        except Exception:
            pass   # keep deterministic result on parse failure

        return result
```

The built-in `build_llm_prompt()` produces a structured, bounded prompt that constrains the LLM to substitution tasks only — not free-form generation.

---

## Schema overview

An **Experience Packet** has three layers:

| Layer | Contents | Purpose |
|---|---|---|
| **Scenario** | task goal, environment signature, symptoms | What was the situation |
| **Failure + Solution** | failure signature, steps, recovery path | What happened and what was done |
| **Transferable Skill** | abstracted pattern, applicability, adaptation hooks | What generalises |

Layer 3 is a **separate abstraction pass** — not a summary of Layers 1 and 2. It deliberately removes context-specific detail to preserve the transferable core.

Full schema: see [SCHEMA.md](./SCHEMA.md) or the paper [experience_md_paper.md](../experience_md_paper.md).

---

## Retrieval scoring

```
S(packet, query) = 0.30 × task_family_similarity
                 + 0.25 × failure_signature_similarity
                 + 0.20 × environment_similarity
                 + 0.10 × tool_similarity
                 + 0.10 × trust_score
                 + 0.05 × recency
```

All weights are configurable. The default token-similarity functions are drop-in replaceable with embedding-based similarity for production use.

---

## Trust model

```
trust_score = base_confidence × 0.4
            + reuse_success_rate × 0.4
            + avg_attribution_score × 0.2
```

**True attribution** corrects for tasks that would have succeeded without the transferred experience:

```
true_attribution = raw_attribution × (1 - base_success_rate_on_similar_tasks)
```

This prevents false positives where the agent succeeded *despite* the transfer rather than *because* of it.

---

## Versioning

Packets use semantic versioning (MAJOR.MINOR.PATCH). Baselines snapshot store state for reproducible experiments:

```python
# All versions retained — pin to any prior state
store.get(packet_id)          # latest
store.get(packet_id, version="0.1.0")   # pinned (coming in v0.2.0)
```

---

## Extending the mapping tables

Add domain-specific substitutions at init time:

```python
adapter = ExperienceAdapter(extra_mappings={
    "provider": {
        ("okta", "auth0"): {
            "Okta Admin Console": "Auth0 Dashboard",
            "OKTA_CLIENT_ID": "AUTH0_CLIENT_ID",
        }
    }
})
```

Or contribute to the built-in tables in `adapt.py`.

---

## Architecture

```
experiencemd/
├── schema.py      — ExperiencePacket and all dataclasses
├── pack.py        — from_episode() factory, PII scrubbing, quality gate
├── store.py       — ExperienceStore, multi-factor retrieval scoring
├── adapt.py       — ExperienceAdapter, env diff, substitution engine
└── __init__.py    — public API

tests/
└── test_experiencemd.py   — 22 tests, all passing

examples/
└── oauth_example.py       — full end-to-end OAuth walkthrough
```

---

## Roadmap

- [ ] **v0.2.0** — YAML/JSON import/export for packets and baselines
- [ ] **v0.2.0** — Packet version pinning in store
- [ ] **v0.3.0** — Embedding-based similarity (drop-in for token similarity)
- [ ] **v0.3.0** — Vector DB backend (Chroma, Qdrant, pgvector)
- [ ] **v0.4.0** — Quantum Experience Mesh (distributed multi-agent store)
- [ ] **v0.4.0** — Counterfactual attribution (automated baseline comparison)
- [ ] **v1.0.0** — Stable schema, community-ratified mapping tables

---

## Contributing

The most valuable contributions right now:

1. **Domain mapping tables** — extend `BUILTIN_MAPPINGS` in `adapt.py` for new provider pairs
2. **Task family definitions** — standard names for common problem classes
3. **Embedding backends** — drop-in replacements for `_text_token_similarity`
4. **Experiment results** — run the benchmark and share your findings

---

## Citation

If you use `experience.md` in research, please cite:

```
@misc{experiencemd2026,
  title  = {experience.md: A Standard for Transferable Agent Experience},
  author = {Quantum Agents Project},
  year   = {2026},
  url    = {https://github.com/quantum-agents/experience-md}
}
```

---

## License

MIT. The standard itself (`experience.md`) is CC0 — use it freely, build on it, contribute back.
