"""HTML renderers — generate HTML artifacts for testament gallery and organ cards.

Uses string templates (no Jinja2 dependency in this module).
Aesthetic cascade governs all visual decisions.
"""

from __future__ import annotations


def render_gallery_page(
    artifacts: list[dict],
    title: str = "ORGANVM Testament Gallery",
    palette: dict | None = None,
) -> str:
    """Render a static HTML gallery page listing all produced artifacts.

    Each artifact dict should have: title, modality, format, path, timestamp, organ.
    """
    p = palette or _default_palette()

    cards_html = []
    for a in artifacts:
        organ = a.get("organ", "system")
        modality = a.get("modality", "unknown")
        fmt = a.get("format", "")
        ts = a.get("timestamp", "")[:10]
        artifact_title = a.get("title", "Untitled")
        path = a.get("path", "")

        # Embed SVGs inline, link others
        if fmt.upper() == "SVG" and path:
            content = f'<div class="artifact-preview"><object data="{path}" type="image/svg+xml"></object></div>'
        else:
            content = f'<div class="artifact-preview placeholder">{modality}</div>'

        cards_html.append(f"""
    <div class="artifact-card">
      <div class="card-header">
        <span class="organ-tag">{organ}</span>
        <span class="modality-tag">{modality}</span>
      </div>
      {content}
      <div class="card-footer">
        <span class="card-title">{_esc(artifact_title)}</span>
        <span class="card-date">{ts}</span>
      </div>
    </div>""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  :root {{
    --bg: {p['background']};
    --surface: {p['secondary']};
    --primary: {p['primary']};
    --accent: {p['accent']};
    --text: {p['text']};
    --muted: {p['muted']};
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    line-height: 1.6;
    padding: 2rem;
  }}
  h1 {{
    font-size: 1.4rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    margin-bottom: 0.5rem;
    color: var(--accent);
  }}
  .subtitle {{
    font-size: 0.8rem;
    color: var(--muted);
    margin-bottom: 2rem;
  }}
  .gallery {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 1.5rem;
  }}
  .artifact-card {{
    background: var(--surface);
    border: 1px solid var(--primary);
    border-radius: 6px;
    overflow: hidden;
    transition: border-color 0.2s;
  }}
  .artifact-card:hover {{
    border-color: var(--accent);
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    padding: 0.6rem 0.8rem;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .organ-tag {{
    color: var(--accent);
  }}
  .modality-tag {{
    color: var(--muted);
  }}
  .artifact-preview {{
    width: 100%;
    min-height: 180px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg);
  }}
  .artifact-preview object {{
    width: 100%;
    max-height: 250px;
  }}
  .placeholder {{
    font-size: 0.9rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }}
  .card-footer {{
    display: flex;
    justify-content: space-between;
    padding: 0.6rem 0.8rem;
    font-size: 0.75rem;
  }}
  .card-title {{
    color: var(--text);
    font-weight: 500;
  }}
  .card-date {{
    color: var(--muted);
  }}
  footer {{
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--primary);
    font-size: 0.7rem;
    color: var(--muted);
    text-align: center;
  }}
</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="subtitle">{len(artifacts)} artifacts — the system renders its own density into experience</p>
<div class="gallery">
{''.join(cards_html)}
</div>
<footer>ORGANVM TESTAMENT — structural self-awareness through continuous self-description</footer>
</body>
</html>"""


def render_testament_page(
    summary: dict,
    title: str = "ORGANVM Testament",
    palette: dict | None = None,
) -> str:
    """Render the stakeholder portal's ``/testament/`` route as an HTML page.

    Takes the dict produced by :func:`organvm_engine.testament.get_testament_summary`
    and renders a self-contained dashboard page (no external assets). Used both
    as a static export and as the payload the portal route serves.
    """
    p = palette or _default_palette()

    system = summary.get("system", {})
    omega = summary.get("omega", {})
    densities = summary.get("densities", {})
    sonic = summary.get("sonic", {})
    catalog = summary.get("catalog", {})
    network = summary.get("network", {})

    met_pct = round(omega.get("met_ratio", 0) * 100)

    def _stat(label: str, value: object) -> str:
        return (
            f'  <div class="stat">'
            f'<span class="stat-value">{_esc(str(value))}</span>'
            f'<span class="stat-label">{_esc(label)}</span></div>'
        )

    overview = "\n".join([
        _stat("Repositories", system.get("total_repos", 0)),
        _stat("Organs", system.get("total_organs", 0)),
        _stat("Public", system.get("total_public", 0)),
        _stat("Omega", f"{omega.get('met_count', 0)}/{omega.get('total', 17)}"),
        _stat("Maturity", f"{met_pct}%"),
        _stat("Artifacts", catalog.get("total", 0)),
    ])

    density_rows = "\n".join(
        f'    <tr><td>{_esc(organ)}</td>'
        f'<td><div class="bar"><div class="bar-fill" style="width:{round(val * 100)}%"></div></div></td>'
        f'<td class="num">{round(val * 100)}%</td></tr>'
        for organ, val in sorted(densities.items(), key=lambda kv: -kv[1])
    ) or '    <tr><td colspan="3" class="muted">no density data</td></tr>'

    exec_order = network.get("execution_order", [])
    exec_html = " → ".join(_esc(str(n)) for n in exec_order) or "—"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  :root {{
    --bg: {p['background']};
    --surface: {p['secondary']};
    --primary: {p['primary']};
    --accent: {p['accent']};
    --text: {p['text']};
    --muted: {p['muted']};
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    line-height: 1.6;
    padding: 2rem;
    max-width: 960px;
    margin: 0 auto;
  }}
  h1 {{
    font-size: 1.5rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    color: var(--accent);
  }}
  .subtitle {{ font-size: 0.8rem; color: var(--muted); margin-bottom: 2rem; }}
  h2 {{
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent);
    margin: 2rem 0 0.8rem;
  }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 1rem;
  }}
  .stat {{
    background: var(--surface);
    border: 1px solid var(--primary);
    border-radius: 6px;
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }}
  .stat-value {{ font-size: 1.6rem; font-weight: 700; color: var(--text); }}
  .stat-label {{
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
  td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--primary); }}
  td.num {{ text-align: right; color: var(--muted); }}
  .muted {{ color: var(--muted); }}
  .bar {{ background: var(--bg); border-radius: 4px; height: 8px; overflow: hidden; }}
  .bar-fill {{ background: var(--accent); height: 100%; }}
  .sonic, .network {{
    background: var(--surface);
    border: 1px solid var(--primary);
    border-radius: 6px;
    padding: 1rem;
    font-size: 0.8rem;
  }}
  footer {{
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--primary);
    font-size: 0.7rem;
    color: var(--muted);
    text-align: center;
  }}
</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p class="subtitle">The system's generative self-portrait — rendered for the stakeholder portal</p>

<h2>Overview</h2>
<div class="stats">
{overview}
</div>

<h2>Organ Density</h2>
<table>
{density_rows}
</table>

<h2>Sonic Self-Portrait</h2>
<div class="sonic">
  {sonic.get('voices', 0)} voices · {sonic.get('bpm', 120)} BPM ·
  {sonic.get('time_signature', '4/4')} · master amplitude {sonic.get('master_amplitude', 0)}
</div>

<h2>Feedback Network</h2>
<div class="network">
  {network.get('nodes', 0)} nodes · {network.get('feedback_edges', 0)} feedback edges<br>
  <span class="muted">execution order:</span> {exec_html}
</div>

<footer>ORGANVM TESTAMENT — structural self-awareness through continuous self-description</footer>
</body>
</html>"""


def render_organ_card_html(
    organ_key: str,
    organ_name: str,
    repo_count: int = 0,
    flagship_count: int = 0,
    status_counts: dict[str, int] | None = None,
    palette: dict | None = None,
) -> str:
    """Render an HTML identity card for a single organ."""
    p = palette or _default_palette()
    statuses = status_counts or {}

    status_rows = "\n".join(
        f'    <tr><td>{_esc(k)}</td><td>{v}</td></tr>'
        for k, v in sorted(statuses.items())
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ORGAN {_esc(organ_key)} — {_esc(organ_name)}</title>
<style>
  body {{
    background: {p['background']};
    color: {p['text']};
    font-family: "SF Mono", monospace;
    padding: 2rem;
    max-width: 480px;
  }}
  .card {{
    border: 1px solid {p['accent']}40;
    border-radius: 8px;
    overflow: hidden;
  }}
  .card-head {{
    background: {p['secondary']};
    padding: 1rem 1.2rem;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .organ-id {{
    color: {p['accent']};
    font-size: 1.2rem;
    font-weight: 700;
  }}
  .organ-name {{
    font-size: 1rem;
    color: {p['text']};
  }}
  .card-body {{
    padding: 1rem 1.2rem;
  }}
  .stat-row {{
    display: flex;
    justify-content: space-between;
    padding: 0.3rem 0;
    font-size: 0.8rem;
    border-bottom: 1px solid {p['primary']};
  }}
  .stat-label {{ color: {p['muted']}; }}
  .stat-value {{ color: {p['text']}; font-weight: 500; }}
  table {{
    width: 100%;
    font-size: 0.75rem;
    margin-top: 0.8rem;
    border-collapse: collapse;
  }}
  td {{
    padding: 0.25rem 0;
    border-bottom: 1px solid {p['primary']};
  }}
  td:first-child {{ color: {p['muted']}; }}
  td:last-child {{ text-align: right; }}
  .footer {{
    text-align: center;
    font-size: 0.65rem;
    color: {p['muted']};
    padding: 0.8rem;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="card-head">
    <span class="organ-id">ORGAN {_esc(organ_key)}</span>
    <span class="organ-name">{_esc(organ_name)}</span>
  </div>
  <div class="card-body">
    <div class="stat-row">
      <span class="stat-label">Repositories</span>
      <span class="stat-value">{repo_count}</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">Flagships</span>
      <span class="stat-value">{flagship_count}</span>
    </div>
    <table>{status_rows}</table>
  </div>
  <div class="footer">ORGANVM TESTAMENT</div>
</div>
</body>
</html>"""


def _esc(s: str) -> str:
    """Escape HTML special characters."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _default_palette() -> dict:
    """Default palette from taste.yaml."""
    return {
        "primary": "#1a1a2e",
        "secondary": "#16213e",
        "accent": "#e94560",
        "background": "#0f0f23",
        "text": "#d4d4d8",
        "muted": "#6b7280",
    }
