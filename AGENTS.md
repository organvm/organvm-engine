<!-- ORGANVM:AUTO:START -->
## Agent Context (auto-generated — do not edit)

This repo participates in the **META-ORGANVM (Meta)** swarm.

### Active Subscriptions
- Event: `registry.updated` → Action: Re-validate registry against governance rules
- Event: `governance.promotion_changed` → Action: Update omega scorecard and context files for promoted repo
- Event: `seed.edge_added` → Action: Re-validate dependency graph for new edge
- Event: `entity.created` → Action: Bootstrap context files and registry entry for new entity
- Event: `metrics.organism_computed` → Action: Propagate computed metrics into markdown/JSON targets
- Event: `ci.health` → Action: Triage CI health changes and update soak dashboard

### Production Responsibilities
- **Produce** `governance-policy` for ORGAN-IV, META-ORGANVM
- **Produce** `registry` for ORGAN-IV, META-ORGANVM
- **Produce** `metrics` for META-ORGANVM
- **Produce** `omega-scorecard` for META-ORGANVM
- **Produce** `context-files` for ORGAN-I, ORGAN-II, ORGAN-III, ORGAN-IV, ORGAN-V, ORGAN-VI, ORGAN-VII, META-ORGANVM
- **Produce** `session-analysis` for META-ORGANVM
- **Produce** `plan-atoms` for META-ORGANVM
- **Produce** `prompt-narratives` for META-ORGANVM
- **Produce** `atom-links` for META-ORGANVM
- **Produce** `testament-artifacts` for META-ORGANVM
- **Produce** `ci-reports` for META-ORGANVM
- **Produce** `pitch-decks` for META-ORGANVM
- **Produce** `ecosystem-profiles` for META-ORGANVM
- **Produce** `fossil-record` for META-ORGANVM
- **Produce** `witness-hooks` for ALL

### External Dependencies
- **Consume** `registry` from `META-ORGANVM`
- **Consume** `schema` from `META-ORGANVM`
- **Consume** `governance-rules` from `META-ORGANVM`
- **Consume** `soak-data` from `META-ORGANVM`
- **Consume** `seed-files` from `META-ORGANVM`
- **Consume** `session-transcripts` from `META-ORGANVM`
- **Consume** `plan-files` from `META-ORGANVM`

### Governance Constraints
- Adhere to unidirectional flow: I→II→III
- Never commit secrets or credentials

*Last synced: 2026-05-23T00:26:31Z*
<!-- ORGANVM:AUTO:END -->
