"""Generate SOP scaffolds for uncovered operational patterns.

Uses the same frontmatter format as cli/sop.py._SOP_INIT_TEMPLATE,
enriched with sample prompts from the user's actual clipboard cuttings.
"""

from __future__ import annotations

from pathlib import Path

from organvm_engine.distill.coverage import CoverageEntry
from organvm_engine.distill.taxonomy import OPERATIONAL_PATTERNS, OperationalPattern


def generate_sop_scaffold(
    pattern: OperationalPattern,
    sample_prompts: list[str] | None = None,
) -> str:
    """Generate a SOP markdown scaffold for a given pattern.

    Args:
        pattern: The operational pattern to scaffold.
        sample_prompts: Optional list of representative prompt texts.

    Returns:
        Complete SOP markdown string with frontmatter.
    """
    name = pattern.sop_name_hint or pattern.id
    title = pattern.label

    lines = [
        "---",
        "sop: true",
        f"name: {name}",
        f"scope: {pattern.scope}",
        f"phase: {pattern.phase}",
        "triggers: []",
        "complements: []",
        "overrides: null",
        "governs: []",
        "---",
        f"# SOP: {title}",
        "",
        "## 1. Ontological Purpose",
        "",
        f"{pattern.description}",
        "",
        "<!-- Cross-reference to governing METADOC: METADOC--sop-ecosystem.md -->",
        "",
        "## 2. Procedure",
        "",
        "<!-- Step-by-step instructions -->",
        "",
        "### Phase 1: Preparation",
        "",
        "1. <!-- Step 1 -->",
        "2. <!-- Step 2 -->",
        "",
        "### Phase 2: Execution",
        "",
        "1. <!-- Step 1 -->",
        "2. <!-- Step 2 -->",
        "",
        "### Phase 3: Verification",
        "",
        "1. <!-- Step 1 -->",
        "2. <!-- Step 2 -->",
        "",
        "## 3. Starter Research Questions",
        "",
        "- <!-- What prior art exists for this workflow? -->",
        "- <!-- What are the common failure modes? -->",
        "- <!-- What tools or skills complement this SOP? -->",
        "",
        "## 4. Output Artifacts",
        "",
        "- <!-- List expected deliverables -->",
        "",
        "## 5. Verification",
        "",
        "<!-- How to confirm the procedure was followed correctly -->",
        "",
    ]

    if sample_prompts:
        lines.extend([
            "## 6. Prompt Examples",
            "",
            "Representative prompts from clipboard history that trigger this pattern:",
            "",
        ])
        for i, prompt_text in enumerate(sample_prompts[:5], 1):
            # Wrap in blockquote, truncate long prompts
            text = prompt_text.replace("\n", "\n> ").strip()
            if len(text) > 500:
                text = text[:500] + "..."
            lines.append(f"### Example {i}")
            lines.append("")
            lines.append(f"> {text}")
            lines.append("")

    return "\n".join(lines)


def generate_scaffolds(
    coverage: list[CoverageEntry],
    output_dir: Path,
    dry_run: bool = True,
) -> list[Path]:
    """Generate SOP scaffold files for all uncovered patterns.

    Args:
        coverage: Coverage entries from analyze_coverage().
        output_dir: Directory to write SOP files into.
        dry_run: If True, report what would be written but don't write.

    Returns:
        List of paths that were (or would be) written.
    """
    written: list[Path] = []

    for entry in coverage:
        if entry.status == "covered":
            continue

        pattern = OPERATIONAL_PATTERNS.get(entry.pattern_id)
        if not pattern:
            continue

        name = pattern.sop_name_hint or pattern.id
        filename = f"SOP--{name}.md"
        target = output_dir / filename

        if target.exists():
            continue

        content = generate_sop_scaffold(pattern, entry.sample_prompts)
        written.append(target)

        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    return written
