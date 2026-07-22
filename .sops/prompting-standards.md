---
sop: true
name: prompting-standards
scope: system
phase: any
last_reviewed: 2026-06-19
governed_paths:
  - src/organvm_engine/prompting/
  - src/organvm_engine/contextmd/
  - tests/test_prompting_standards.py
triggers: []
complements: []
overrides: null
---
# Prompting Standards

## Purpose

Governs how the ORGANVM system generates prompts and context files for different AI providers.
Ensures each agent (Claude, Gemini, ChatGPT, Grok, Perplexity) receives optimally structured
input following that provider's documented best practices.

## Key Findings

- **Anthropic (Claude)**: Prefers XML tags for structure, supports extended thinking, 200K context
- **Google (Gemini)**: Leverages 1M token context, grounding with Search, structured output schemas
- **OpenAI (GPT-4o)**: Markdown with delimiters, structured outputs via json_schema, 128K context
- **Grok**: Real-time X/Twitter data, DeepSearch, think mode with budget_tokens
- **Perplexity**: Search-augmented generation, domain/recency filters, automatic citations

## Procedure

1. When generating context files (`organvm context sync`), inject provider-specific hints
2. Use `organvm_engine.prompting.loader.load_guidelines(agent)` to retrieve standards
3. Format guidelines via `format_guidelines_hint()` for lightweight injection
4. For full guidelines, reference `organvm_engine.prompting.standards.PROVIDER_GUIDELINES`

## Verification

- `from organvm_engine.prompting.standards import PROVIDER_GUIDELINES` succeeds
- `organvm sop discover --json | grep prompting` finds this SOP
- Context sync injects provider hints into generated CLAUDE.md / GEMINI.md files
