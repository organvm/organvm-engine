"""Discovery of parallel and kinship mirrors.

Technical mirrors are automated by scanner.py (dependency files).
This module handles the other two lenses:
- Parallel: projects solving similar problems (semi-automated)
- Kinship: communities with philosophical alignment (human-confirmed)

Discovery uses seed.yaml tags, ecosystem taxonomy, and registry
metadata to suggest mirrors for human review.
"""

from __future__ import annotations

from organvm_engine.network.schema import MirrorEntry

# Domain → relevant parallel projects mapping
# Expanded by research (issues #65, #66); curated real-world projects per domain.
PARALLEL_PROJECTS: dict[str, list[dict]] = {
    "multi-repo-governance": [
        {"project": "lerna/lerna", "relevance": "JS monorepo orchestration"},
        {"project": "nrwl/nx", "relevance": "Smart monorepo build system"},
        {"project": "vercel/turborepo", "relevance": "High-performance monorepo builds"},
        {"project": "pantsbuild/pants", "relevance": "Polyglot monorepo build system"},
        {"project": "aspect-build/bazel-lib", "relevance": "Bazel build extensions"},
        {"project": "changesets/changesets", "relevance": "Versioning and changelog for monorepos"},
        {"project": "nicolo-ribaudo/chores-bot", "relevance": "Monorepo task automation"},
        {"project": "pnpm/pnpm", "relevance": "Workspace-aware package manager"},
        {"project": "nicknisi/dotfiles", "relevance": "Multi-machine config orchestration pattern"},
        {"project": "backstage/backstage", "relevance": "Developer portal with multi-repo catalog"},
        {"project": "moonrepo/moon", "relevance": "Repository management and task runner"},
        {"project": "earthly/earthly", "relevance": "Reproducible builds for polyglot repos"},
    ],
    "mcp-server": [
        {"project": "modelcontextprotocol/servers", "relevance": "Official MCP server implementations"},
        {"project": "modelcontextprotocol/python-sdk", "relevance": "MCP Python SDK"},
        {"project": "modelcontextprotocol/typescript-sdk", "relevance": "MCP TypeScript SDK"},
        {"project": "modelcontextprotocol/specification", "relevance": "MCP protocol specification"},
        {"project": "modelcontextprotocol/inspector", "relevance": "MCP debugging and inspection tool"},
        {
            "project": "punkpeye/awesome-mcp-servers",
            "relevance": "Community-curated MCP server directory",
        },
        {"project": "mark3labs/mcp-go", "relevance": "MCP SDK for Go"},
        {
            "project": "modelcontextprotocol/create-python-server",
            "relevance": "MCP server scaffolding CLI",
        },
        {
            "project": "wong2/mcp-cli",
            "relevance": "CLI client for testing MCP servers",
        },
        {
            "project": "zed-industries/zed",
            "relevance": "Editor with native MCP integration",
        },
        {
            "project": "continuedev/continue",
            "relevance": "AI code assistant with MCP support",
        },
    ],
    "generative-art": [
        {"project": "processing/p5.js", "relevance": "Creative coding library"},
        {"project": "nannou-org/nannou", "relevance": "Creative coding in Rust"},
        {"project": "openframeworks/openFrameworks", "relevance": "Creative coding C++ toolkit"},
        {"project": "mattdesl/canvas-sketch", "relevance": "Framework for generative art sketches"},
        {"project": "spite/ccapture.js", "relevance": "Canvas capture for generative art export"},
        {"project": "georgedoescode/generative-utils", "relevance": "Utility library for generative art"},
        {"project": "inconvergent/weir", "relevance": "Graph-based generative system in CL"},
        {"project": "sighack/processing-sketches", "relevance": "Curated generative Processing sketches"},
        {"project": "mattdesl/three-bmfont-text", "relevance": "3D text for creative coding"},
        {"project": "aframevr/aframe", "relevance": "WebXR framework for immersive art"},
        {"project": "patriciogonzalezvivo/glslCanvas", "relevance": "GLSL shader sandbox for art"},
        {"project": "spite/Wagner", "relevance": "WebGL post-processing for creative visuals"},
        {"project": "terkelg/awesome-creative-coding", "relevance": "Community index of creative coding"},
    ],
    "ai-orchestration": [
        {"project": "langchain-ai/langchain", "relevance": "LLM application framework"},
        {"project": "microsoft/autogen", "relevance": "Multi-agent AI framework"},
        {"project": "stanfordnlp/dspy", "relevance": "Programming with foundation models"},
        {"project": "crewAIInc/crewAI", "relevance": "Role-based multi-agent orchestration"},
        {"project": "joaomdmoura/crewAI-tools", "relevance": "Tool library for CrewAI agents"},
        {"project": "BerriAI/litellm", "relevance": "Unified LLM API proxy and routing"},
        {"project": "openai/swarm", "relevance": "Lightweight multi-agent framework"},
        {"project": "run-llama/llama_index", "relevance": "Data framework for LLM applications"},
        {"project": "vllm-project/vllm", "relevance": "High-throughput LLM serving engine"},
        {
            "project": "huggingface/transformers",
            "relevance": "Foundation model library for ML pipelines",
        },
        {
            "project": "instructor-ai/instructor",
            "relevance": "Structured output extraction from LLMs",
        },
        {"project": "pydantic/pydantic-ai", "relevance": "Type-safe agent framework for Python"},
        {"project": "letta-ai/letta", "relevance": "Stateful LLM agents with memory"},
    ],
    "registry-governance": [
        {"project": "open-policy-agent/opa", "relevance": "Policy-as-code engine"},
        {"project": "cerbos/cerbos", "relevance": "Authorization policy engine"},
        {"project": "hashicorp/sentinel", "relevance": "Policy-as-code for Terraform"},
        {"project": "bridgecrewio/checkov", "relevance": "IaC policy scanning"},
        {"project": "aquasecurity/trivy", "relevance": "Security and compliance scanning"},
        {
            "project": "ossf/scorecard",
            "relevance": "OSS project health scorecard",
        },
        {
            "project": "todogroup/repolinter",
            "relevance": "Repository compliance linter",
        },
        {
            "project": "github/github-ospo",
            "relevance": "Open source program office tooling",
        },
        {
            "project": "spotify/backstage-plugin-catalog-backend",
            "relevance": "Service catalog governance for Backstage",
        },
        {
            "project": "probot/probot",
            "relevance": "GitHub App framework for repo governance",
        },
        {"project": "atlas-org/atlas", "relevance": "Declarative database schema governance"},
        {
            "project": "styra/das-opa-samples",
            "relevance": "OPA decision logging and audit",
        },
    ],
    "schema-validation": [
        {"project": "json-schema-org/json-schema-spec", "relevance": "JSON Schema specification"},
        {"project": "pydantic/pydantic", "relevance": "Python data validation with schemas"},
        {"project": "ajv-validator/ajv", "relevance": "Fastest JSON Schema validator for JS"},
        {
            "project": "python-jsonschema/jsonschema",
            "relevance": "JSON Schema validation for Python",
        },
        {
            "project": "APIDevTools/json-schema-ref-parser",
            "relevance": "JSON Schema $ref resolution",
        },
        {"project": "typeschema/typeschema", "relevance": "Cross-language schema translation"},
        {"project": "asyncapi/spec", "relevance": "Async API schema specification"},
        {"project": "OAI/OpenAPI-Specification", "relevance": "REST API schema specification"},
        {"project": "buf-build/buf", "relevance": "Protobuf schema linting and breaking change detection"},
        {
            "project": "cedar-policy/cedar",
            "relevance": "Policy language with schema-driven validation",
        },
        {
            "project": "typeddjango/djangorestframework-stubs",
            "relevance": "Typed schema validation for DRF",
        },
    ],
    "session-analysis": [
        {"project": "brainlid/langchain", "relevance": "Conversation chain analysis"},
        {"project": "langfuse/langfuse", "relevance": "LLM observability and session tracing"},
        {
            "project": "traceloop/openllmetry",
            "relevance": "OpenTelemetry instrumentation for LLMs",
        },
        {"project": "whylabs/langkit", "relevance": "LLM telemetry and monitoring"},
        {
            "project": "parea-ai/parea-sdk-py",
            "relevance": "LLM session evaluation and testing",
        },
        {"project": "promptfoo/promptfoo", "relevance": "LLM prompt testing and evaluation"},
        {
            "project": "arize-ai/phoenix",
            "relevance": "ML/LLM observability with session replay",
        },
        {"project": "wandb/weave", "relevance": "LLM application tracing by Weights & Biases"},
        {
            "project": "lunary-ai/lunary",
            "relevance": "Open-source LLM session analytics",
        },
        {
            "project": "helicone-ai/helicone",
            "relevance": "LLM request logging and cost analysis",
        },
    ],
    "dashboard-monitoring": [
        {"project": "grafana/grafana", "relevance": "Observability dashboards"},
        {"project": "apache/superset", "relevance": "Data visualization platform"},
        {"project": "metabase/metabase", "relevance": "Open-source BI and dashboards"},
        {"project": "louislam/uptime-kuma", "relevance": "Self-hosted uptime monitoring"},
        {"project": "netdata/netdata", "relevance": "Real-time infrastructure monitoring"},
        {
            "project": "gethomepage/homepage",
            "relevance": "Self-hosted service dashboard",
        },
        {
            "project": "prometheus/prometheus",
            "relevance": "Metrics collection and alerting",
        },
        {"project": "PostHog/posthog", "relevance": "Open-source product analytics platform"},
        {"project": "directus/directus", "relevance": "Data studio with dashboard builder"},
        {"project": "redash/redash", "relevance": "Query-based data visualization"},
        {
            "project": "umami-software/umami",
            "relevance": "Privacy-focused web analytics",
        },
    ],
    "content-pipeline": [
        {"project": "getpelican/pelican", "relevance": "Static site generator for content"},
        {"project": "withastro/astro", "relevance": "Content-focused web framework"},
        {"project": "gohugoio/hugo", "relevance": "Fast static site generator"},
        {"project": "11ty/eleventy", "relevance": "Simpler static site generator"},
        {"project": "keystonejs/keystone", "relevance": "Headless CMS and content API"},
        {"project": "strapi/strapi", "relevance": "Open-source headless CMS"},
        {"project": "sanity-io/sanity", "relevance": "Structured content platform"},
        {
            "project": "tinacms/tinacms",
            "relevance": "Git-backed headless CMS",
        },
        {
            "project": "decaporg/decap-cms",
            "relevance": "Open-source Git-based CMS (formerly Netlify CMS)",
        },
        {"project": "payloadcms/payload", "relevance": "TypeScript headless CMS"},
        {
            "project": "outline/outline",
            "relevance": "Wiki and knowledge base with API",
        },
        {
            "project": "writefreely/writefreely",
            "relevance": "Federated writing platform (ActivityPub)",
        },
    ],
    "knowledge-graph": [
        {"project": "neo4j/neo4j", "relevance": "Graph database"},
        {"project": "oxigraph/oxigraph", "relevance": "RDF/SPARQL graph store in Rust"},
        {"project": "logseq/logseq", "relevance": "Knowledge graph notebook"},
        {"project": "obsidianmd/obsidian-releases", "relevance": "Knowledge graph via linked notes"},
        {"project": "dendronhq/dendron", "relevance": "Hierarchical knowledge management"},
        {
            "project": "memgraph/memgraph",
            "relevance": "In-memory graph database",
        },
        {"project": "dgraph-io/dgraph", "relevance": "Distributed graph database"},
        {
            "project": "apache/tinkerpop",
            "relevance": "Graph computing framework (Gremlin)",
        },
        {"project": "athensresearch/athens", "relevance": "Open-source networked thought tool"},
        {"project": "foambubble/foam", "relevance": "VS Code knowledge graph extension"},
        {
            "project": "bram-adams/incremental-knowledge",
            "relevance": "Research on incremental knowledge systems",
        },
        {
            "project": "surrealdb/surrealdb",
            "relevance": "Multi-model DB with graph capabilities",
        },
    ],
    "institutional-design": [
        {
            "project": "aragon/aragon-app",
            "relevance": "DAO governance framework",
        },
        {
            "project": "snapshot-labs/snapshot",
            "relevance": "Off-chain governance voting",
        },
        {
            "project": "gitcoinco/gitcoin",
            "relevance": "Public goods funding and governance",
        },
        {
            "project": "compound-finance/compound-governance",
            "relevance": "On-chain governance protocol",
        },
        {
            "project": "openzeppelin/openzeppelin-contracts",
            "relevance": "Governance contract primitives",
        },
        {
            "project": "makerdao/governance-portal-v2",
            "relevance": "MakerDAO governance portal",
        },
        {
            "project": "RadicalxChange/plural-money",
            "relevance": "RadicalxChange plural governance experiments",
        },
        {
            "project": "DemocracyEarth/paper",
            "relevance": "Liquid democracy and digital governance",
        },
        {
            "project": "loomio/loomio",
            "relevance": "Cooperative decision-making platform",
        },
        {
            "project": "pol-is/polis",
            "relevance": "Large-scale deliberation and opinion mapping",
        },
    ],
}

# Kinship communities — philosophical alignment, not technology.
# Organized by organ affinity (issues #65, #66; R3 round #66 / LIMEN-070). A
# community may align with multiple organs; the primary organ tag is listed first.
KINSHIP_COMMUNITIES: list[dict] = [
    # ── Cross-organ / system-wide ────────────────────────────────────────
    {
        "project": "indieweb",
        "platform": "community",
        "relevance": "POSSE principles — own your content, syndicate everywhere",
        "url": "https://indieweb.org",
        "tags": ["posse", "content-ownership", "decentralization"],
        "organs": ["V", "VII"],
    },
    {
        "project": "small-tech-foundation",
        "platform": "community",
        "relevance": "Solo-operator infrastructure, anti-platform philosophy",
        "url": "https://small-tech.org",
        "tags": ["solo-operator", "small-tech", "ethical-tech"],
        "organs": ["III", "META"],
    },
    {
        "project": "open-source-sustainability",
        "platform": "community",
        "relevance": "Open Collective, GitHub Sponsors ecosystem — sustaining OSS",
        "url": "https://opencollective.com",
        "tags": ["oss-sustainability", "funding", "commons"],
        "organs": ["III", "META"],
    },
    {
        "project": "cooperatives-tech",
        "platform": "community",
        "relevance": "Platform Cooperativism Consortium — tech cooperatives and democratic ownership",
        "url": "https://platform.coop",
        "tags": ["cooperatives", "governance", "institutional-design"],
        "organs": ["META", "IV"],
    },
    # ── ORGAN-I: Theoria — philosophy of technology, systems theory, epistemology ──
    {
        "project": "tools-for-thought",
        "platform": "community",
        "relevance": "Knowledge management, second brain, networked thought",
        "url": "https://www.reddit.com/r/ToolsForThought/",
        "tags": ["knowledge-management", "pkm", "note-taking"],
        "organs": ["I"],
    },
    {
        "project": "digital-humanities",
        "platform": "community",
        "relevance": "ADHO / Alliance of Digital Humanities Organizations",
        "url": "https://adho.org",
        "tags": ["digital-humanities", "academic", "text-analysis"],
        "organs": ["I", "V"],
    },
    {
        "project": "santa-fe-institute",
        "platform": "community",
        "relevance": "Complexity science research — systems theory and emergence",
        "url": "https://santafe.edu",
        "tags": ["complexity", "systems-theory", "emergence"],
        "organs": ["I"],
    },
    {
        "project": "cybernetics-society",
        "platform": "community",
        "relevance": "American Society for Cybernetics — second-order cybernetics",
        "url": "https://asc-cybernetics.org",
        "tags": ["cybernetics", "systems-theory", "self-organization"],
        "organs": ["I"],
    },
    {
        "project": "long-now-foundation",
        "platform": "community",
        "relevance": "Long-term thinking and civilizational time scales",
        "url": "https://longnow.org",
        "tags": ["long-term-thinking", "civilization", "archives"],
        "organs": ["I", "META"],
    },
    {
        "project": "nlab-community",
        "platform": "wiki",
        "relevance": "nLab — collaborative wiki for higher category theory and mathematics",
        "url": "https://ncatlab.org",
        "tags": ["category-theory", "mathematics", "formal-systems"],
        "organs": ["I"],
    },
    {
        "project": "internet-archive",
        "platform": "community",
        "relevance": "Universal knowledge access and digital preservation",
        "url": "https://archive.org",
        "tags": ["archival", "knowledge-access", "digital-preservation"],
        "organs": ["I", "V"],
    },
    {
        "project": "philosophy-of-computer-science",
        "platform": "community",
        "relevance": "International Association for Computing and Philosophy",
        "url": "https://iacap.org",
        "tags": ["philosophy-of-tech", "computation", "ethics"],
        "organs": ["I"],
    },
    # ── ORGAN-II: Poiesis — creative coding, new media art, sound art ────
    {
        "project": "sfpc",
        "platform": "community",
        "relevance": "School for Poetic Computation — artist-technologist collective",
        "url": "https://sfpc.study",
        "tags": ["art-tech", "creative-coding", "education"],
        "organs": ["II", "VI"],
    },
    {
        "project": "gray-area",
        "platform": "community",
        "relevance": "Art + technology incubator and cultural center",
        "url": "https://grayarea.org",
        "tags": ["art-tech", "incubator", "digital-art"],
        "organs": ["II"],
    },
    {
        "project": "eyebeam",
        "platform": "community",
        "relevance": "Art + technology center fostering creative practice",
        "url": "https://eyebeam.org",
        "tags": ["art-tech", "residency", "new-media"],
        "organs": ["II"],
    },
    {
        "project": "creative-coding-community",
        "platform": "discord",
        "relevance": "Creative coding practitioners — generative art, interactive media",
        "url": "https://discord.gg/creativecoding",
        "tags": ["creative-coding", "generative-art", "community"],
        "organs": ["II"],
    },
    {
        "project": "lines-community",
        "platform": "forum",
        "relevance": "Monome/llllllll — modular synthesis, algorithmic music, sound art",
        "url": "https://llllllll.co",
        "tags": ["modular-synthesis", "sound-art", "algorithmic-music"],
        "organs": ["II"],
    },
    {
        "project": "processing-foundation",
        "platform": "community",
        "relevance": "Processing Foundation — creative coding education and tools",
        "url": "https://processingfoundation.org",
        "tags": ["creative-coding", "education", "visual-arts"],
        "organs": ["II", "VI"],
    },
    {
        "project": "toplap",
        "platform": "community",
        "relevance": "TOPLAP — live coding performance community",
        "url": "https://toplap.org",
        "tags": ["live-coding", "performance", "algorithmic-music"],
        "organs": ["II"],
    },
    {
        "project": "ars-electronica",
        "platform": "community",
        "relevance": "Ars Electronica — art, technology, and society festival",
        "url": "https://ars.electronica.art",
        "tags": ["art-tech", "new-media", "festival"],
        "organs": ["II"],
    },
    {
        "project": "creative-applications-network",
        "platform": "community",
        "relevance": "CAN — curated platform for creative technology projects",
        "url": "https://www.creativeapplications.net",
        "tags": ["creative-coding", "new-media", "art-tech"],
        "organs": ["II"],
    },
    {
        "project": "tidalcycles",
        "platform": "community",
        "relevance": "TidalCycles — live coding pattern language for music",
        "url": "https://tidalcycles.org",
        "tags": ["live-coding", "algorithmic-music", "pattern-language"],
        "organs": ["II"],
    },
    {
        "project": "supercollider-community",
        "platform": "forum",
        "relevance": "SuperCollider community — audio synthesis and algorithmic composition",
        "url": "https://scsynth.org",
        "tags": ["sound-art", "algorithmic-music", "audio-synthesis"],
        "organs": ["II"],
    },
    # ── ORGAN-III: Ergon — indie hackers, solo SaaS, micro-ISV ──────────
    {
        "project": "indie-hackers",
        "platform": "forum",
        "relevance": "Indie Hackers — solo founders building profitable businesses",
        "url": "https://indiehackers.com",
        "tags": ["indie-hacker", "solo-saas", "bootstrapping"],
        "organs": ["III"],
    },
    {
        "project": "microconf",
        "platform": "community",
        "relevance": "MicroConf — conference for self-funded SaaS founders",
        "url": "https://microconf.com",
        "tags": ["solo-saas", "bootstrapping", "micro-isv"],
        "organs": ["III"],
    },
    {
        "project": "hackernews",
        "platform": "forum",
        "relevance": "Hacker News — tech community for builders and founders",
        "url": "https://news.ycombinator.com",
        "tags": ["tech-community", "startups", "open-source"],
        "organs": ["III"],
    },
    {
        "project": "product-hunt",
        "platform": "community",
        "relevance": "Product Hunt — product launch and discovery platform",
        "url": "https://producthunt.com",
        "tags": ["product-launch", "solo-saas", "discovery"],
        "organs": ["III", "VII"],
    },
    {
        "project": "wip-chat",
        "platform": "community",
        "relevance": "WIP — makers community for shipping products",
        "url": "https://wip.co",
        "tags": ["makers", "shipping", "accountability"],
        "organs": ["III"],
    },
    {
        "project": "calm-company-fund",
        "platform": "community",
        "relevance": "Calm Fund — funding calm, sustainable software companies",
        "url": "https://calmfund.com",
        "tags": ["calm-tech", "sustainable-business", "bootstrapping"],
        "organs": ["III"],
    },
    {
        "project": "saastr",
        "platform": "community",
        "relevance": "SaaStr — SaaS community and knowledge sharing",
        "url": "https://saastr.com",
        "tags": ["saas", "growth", "community"],
        "organs": ["III"],
    },
    # ── ORGAN-IV: Taxis — DevOps, platform engineering, IaC ─────────────
    {
        "project": "cncf",
        "platform": "community",
        "relevance": "Cloud Native Computing Foundation — cloud-native ecosystem governance",
        "url": "https://cncf.io",
        "tags": ["cloud-native", "orchestration", "infrastructure"],
        "organs": ["IV"],
    },
    {
        "project": "platform-engineering",
        "platform": "community",
        "relevance": "Platform Engineering community — internal developer platforms",
        "url": "https://platformengineering.org",
        "tags": ["platform-engineering", "devops", "developer-experience"],
        "organs": ["IV"],
    },
    {
        "project": "devops-community",
        "platform": "community",
        "relevance": "DevOps Institute and community of practice",
        "url": "https://devopsinstitute.com",
        "tags": ["devops", "sre", "continuous-delivery"],
        "organs": ["IV"],
    },
    {
        "project": "cd-foundation",
        "platform": "community",
        "relevance": "Continuous Delivery Foundation — CI/CD ecosystem",
        "url": "https://cd.foundation",
        "tags": ["continuous-delivery", "cicd", "automation"],
        "organs": ["IV"],
    },
    {
        "project": "github-actions-community",
        "platform": "forum",
        "relevance": "GitHub Actions ecosystem — CI/CD and automation",
        "url": "https://github.com/orgs/community/discussions/categories/actions",
        "tags": ["github-actions", "cicd", "automation"],
        "organs": ["IV"],
    },
    {
        "project": "internal-developer-platform",
        "platform": "community",
        "relevance": "IDP community — Backstage, Humanitec, and platform abstractions",
        "url": "https://internaldeveloperplatform.org",
        "tags": ["platform-engineering", "developer-portal", "service-catalog"],
        "organs": ["IV"],
    },
    {
        "project": "opentofu",
        "platform": "community",
        "relevance": "OpenTofu — open-source infrastructure-as-code",
        "url": "https://opentofu.org",
        "tags": ["infrastructure-as-code", "iac", "open-source"],
        "organs": ["IV"],
    },
    # ── ORGAN-V: Logos — digital publishing, open journalism, POSSE ─────
    {
        "project": "write-as",
        "platform": "community",
        "relevance": "Write.as / WriteFreely — federated, minimal blogging platform",
        "url": "https://write.as",
        "tags": ["publishing", "fediverse", "minimal-writing"],
        "organs": ["V"],
    },
    {
        "project": "ghost-foundation",
        "platform": "community",
        "relevance": "Ghost — open-source publishing platform and creator economy",
        "url": "https://ghost.org",
        "tags": ["publishing", "creator-economy", "open-source"],
        "organs": ["V"],
    },
    {
        "project": "substack-writers",
        "platform": "community",
        "relevance": "Independent newsletter writers and essayists community",
        "url": "https://substack.com",
        "tags": ["newsletters", "essays", "independent-media"],
        "organs": ["V"],
    },
    {
        "project": "webmention-community",
        "platform": "community",
        "relevance": "Webmention — cross-site conversation protocol for the open web",
        "url": "https://webmention.net",
        "tags": ["posse", "open-web", "decentralization"],
        "organs": ["V", "VII"],
    },
    {
        "project": "are-na",
        "platform": "community",
        "relevance": "Are.na — collaborative research and idea curation",
        "url": "https://are.na",
        "tags": ["curation", "research", "knowledge-sharing"],
        "organs": ["V", "I"],
    },
    {
        "project": "creative-commons",
        "platform": "community",
        "relevance": "Creative Commons — open licensing for creative work",
        "url": "https://creativecommons.org",
        "tags": ["open-licensing", "commons", "publishing"],
        "organs": ["V"],
    },
    {
        "project": "journalism-tools",
        "platform": "community",
        "relevance": "Knight Lab and investigative journalism toolmakers",
        "url": "https://knightlab.northwestern.edu",
        "tags": ["journalism", "data-viz", "storytelling"],
        "organs": ["V"],
    },
    # ── ORGAN-VI: Koinonia — learning communities, book clubs, ed-tech ──
    {
        "project": "recurse-center",
        "platform": "community",
        "relevance": "Recurse Center — self-directed programming retreat community",
        "url": "https://recurse.com",
        "tags": ["education", "self-directed-learning", "programming"],
        "organs": ["VI"],
    },
    {
        "project": "coding-train",
        "platform": "community",
        "relevance": "The Coding Train — creative coding education by Daniel Shiffman",
        "url": "https://thecodingtrain.com",
        "tags": ["education", "creative-coding", "tutorials"],
        "organs": ["VI", "II"],
    },
    {
        "project": "freeCodeCamp",
        "platform": "community",
        "relevance": "freeCodeCamp — free coding education and community",
        "url": "https://freecodecamp.org",
        "tags": ["education", "open-source", "learn-to-code"],
        "organs": ["VI"],
    },
    {
        "project": "open-education-network",
        "platform": "community",
        "relevance": "OER Commons — open educational resources network",
        "url": "https://oercommons.org",
        "tags": ["open-education", "oer", "learning-commons"],
        "organs": ["VI"],
    },
    {
        "project": "reading-groups-community",
        "platform": "community",
        "relevance": "Tech reading groups — papers we love, book clubs",
        "url": "https://paperswelove.org",
        "tags": ["reading-groups", "papers", "academic-discourse"],
        "organs": ["VI", "I"],
    },
    {
        "project": "p2pu",
        "platform": "community",
        "relevance": "Peer 2 Peer University — community-led learning circles",
        "url": "https://p2pu.org",
        "tags": ["peer-learning", "learning-circles", "education"],
        "organs": ["VI"],
    },
    {
        "project": "edx-open-source",
        "platform": "community",
        "relevance": "Open edX — open-source online learning platform",
        "url": "https://openedx.org",
        "tags": ["education", "open-source", "online-learning"],
        "organs": ["VI"],
    },
    # ── ORGAN-VII: Kerygma — POSSE distribution, social automation ──────
    {
        "project": "fediverse-community",
        "platform": "community",
        "relevance": "Fediverse — ActivityPub-based social network federation",
        "url": "https://fediverse.info",
        "tags": ["fediverse", "activitypub", "decentralization"],
        "organs": ["VII"],
    },
    {
        "project": "mastodon",
        "platform": "community",
        "relevance": "Mastodon — federated social network, POSSE target",
        "url": "https://joinmastodon.org",
        "tags": ["fediverse", "social-media", "decentralization"],
        "organs": ["VII"],
    },
    {
        "project": "bluesky-community",
        "platform": "community",
        "relevance": "Bluesky / AT Protocol — decentralized social web",
        "url": "https://bsky.app",
        "tags": ["decentralization", "social-web", "at-protocol"],
        "organs": ["VII"],
    },
    {
        "project": "micropub-community",
        "platform": "community",
        "relevance": "Micropub — IndieWeb publishing protocol for syndication",
        "url": "https://micropub.net",
        "tags": ["posse", "indieweb", "syndication"],
        "organs": ["VII", "V"],
    },
    {
        "project": "bridgy",
        "platform": "community",
        "relevance": "Bridgy — POSSE backfeed from social silos to personal sites",
        "url": "https://brid.gy",
        "tags": ["posse", "backfeed", "syndication"],
        "organs": ["VII"],
    },
    {
        "project": "ifttt-maker-community",
        "platform": "community",
        "relevance": "IFTTT and Zapier automation community patterns",
        "url": "https://ifttt.com",
        "tags": ["automation", "syndication", "integration"],
        "organs": ["VII"],
    },
    # ── META / Governance ────────────────────────────────────────────────
    {
        "project": "todo-group",
        "platform": "community",
        "relevance": "TODO Group — open source program office community",
        "url": "https://todogroup.org",
        "tags": ["open-source", "governance", "institutional-design"],
        "organs": ["META"],
    },
    {
        "project": "chaoss",
        "platform": "community",
        "relevance": "CHAOSS — community health analytics for open source",
        "url": "https://chaoss.community",
        "tags": ["oss-health", "metrics", "governance"],
        "organs": ["META"],
    },
    {
        "project": "innersource-commons",
        "platform": "community",
        "relevance": "InnerSource Commons — applying OSS practices inside organizations",
        "url": "https://innersourcecommons.org",
        "tags": ["innersource", "governance", "institutional-design"],
        "organs": ["META"],
    },
    {
        "project": "open-source-initiative",
        "platform": "community",
        "relevance": "OSI — stewardship of open source definition and licensing",
        "url": "https://opensource.org",
        "tags": ["open-source", "licensing", "commons"],
        "organs": ["META"],
    },
    # ══ R3 research round (LIMEN-070, issue #66) ═════════════════════════════
    # Third community-identification pass. Curated, verifiable communities that
    # deepen per-organ kinship coverage and add cross-organ commons.
    # ── Cross-organ / system-wide ────────────────────────────────────────
    {
        "project": "sustainoss",
        "platform": "community",
        "relevance": "Sustain — gathering for open source maintainers and sustainers",
        "url": "https://sustainoss.org",
        "tags": ["oss-sustainability", "maintainers", "commons"],
        "organs": ["META", "III"],
    },
    {
        "project": "permacomputing",
        "platform": "community",
        "relevance": "Permacomputing — sustainable, minimal, resilient computing practice",
        "url": "https://permacomputing.net",
        "tags": ["permacomputing", "sustainability", "minimal-computing"],
        "organs": ["I", "IV", "META"],
    },
    {
        "project": "solid-project",
        "platform": "community",
        "relevance": "Solid — decentralized data ownership for the web (Tim Berners-Lee)",
        "url": "https://solidproject.org",
        "tags": ["data-ownership", "decentralization", "open-web"],
        "organs": ["V", "VII"],
    },
    {
        "project": "digital-gardeners",
        "platform": "community",
        "relevance": "Digital gardens — public, evolving personal knowledge spaces",
        "url": "https://github.com/MaggieAppleton/digital-gardeners",
        "tags": ["digital-gardens", "pkm", "knowledge-sharing"],
        "organs": ["I", "V"],
    },
    # ── ORGAN-I: Theoria ─────────────────────────────────────────────────
    {
        "project": "lesswrong",
        "platform": "forum",
        "relevance": "LessWrong — rationality, epistemology, and decision theory",
        "url": "https://lesswrong.com",
        "tags": ["rationality", "epistemology", "decision-theory"],
        "organs": ["I"],
    },
    {
        "project": "principia-cybernetica",
        "platform": "wiki",
        "relevance": "Principia Cybernetica — evolutionary-systemic philosophy collaborative",
        "url": "http://pespmc1.vub.ac.be",
        "tags": ["cybernetics", "systems-theory", "evolution"],
        "organs": ["I"],
    },
    {
        "project": "metagov",
        "platform": "community",
        "relevance": "Metagovernance Project — research on governance of online communities",
        "url": "https://metagov.org",
        "tags": ["governance", "online-communities", "research"],
        "organs": ["I", "META"],
    },
    # ── ORGAN-II: Poiesis ────────────────────────────────────────────────
    {
        "project": "openprocessing",
        "platform": "community",
        "relevance": "OpenProcessing — community archive for creative-coding sketches",
        "url": "https://openprocessing.org",
        "tags": ["creative-coding", "generative-art", "sketch-sharing"],
        "organs": ["II"],
    },
    {
        "project": "hydra-community",
        "platform": "community",
        "relevance": "Hydra — live-coding networked visuals community",
        "url": "https://hydra.ojack.xyz",
        "tags": ["live-coding", "visuals", "generative-art"],
        "organs": ["II"],
    },
    {
        "project": "nime",
        "platform": "community",
        "relevance": "NIME — New Interfaces for Musical Expression research community",
        "url": "https://nime.org",
        "tags": ["sound-art", "musical-instruments", "research"],
        "organs": ["II", "I"],
    },
    # ── ORGAN-III: Ergon ─────────────────────────────────────────────────
    {
        "project": "tinyseed",
        "platform": "community",
        "relevance": "TinySeed — accelerator and community for bootstrapped SaaS founders",
        "url": "https://tinyseed.com",
        "tags": ["bootstrapping", "solo-saas", "micro-isv"],
        "organs": ["III"],
    },
    {
        "project": "open-startups",
        "platform": "community",
        "relevance": "Open Startups — transparent metrics movement for indie founders",
        "url": "https://openstartups.co",
        "tags": ["transparency", "indie-hacker", "metrics"],
        "organs": ["III", "V"],
    },
    # ── ORGAN-IV: Taxis ──────────────────────────────────────────────────
    {
        "project": "opentelemetry-community",
        "platform": "community",
        "relevance": "OpenTelemetry — vendor-neutral observability instrumentation",
        "url": "https://opentelemetry.io/community",
        "tags": ["observability", "instrumentation", "cloud-native"],
        "organs": ["IV"],
    },
    {
        "project": "opengitops",
        "platform": "community",
        "relevance": "OpenGitOps — CNCF working group defining GitOps principles",
        "url": "https://opengitops.dev",
        "tags": ["gitops", "continuous-delivery", "infrastructure-as-code"],
        "organs": ["IV"],
    },
    {
        "project": "srecon",
        "platform": "community",
        "relevance": "USENIX SREcon — site reliability engineering practitioner community",
        "url": "https://usenix.org/srecon",
        "tags": ["sre", "reliability", "devops"],
        "organs": ["IV"],
    },
    # ── ORGAN-V: Logos ───────────────────────────────────────────────────
    {
        "project": "humanities-commons",
        "platform": "community",
        "relevance": "Humanities Commons — open scholarly network and repository",
        "url": "https://hcommons.org",
        "tags": ["academic", "publishing", "commons"],
        "organs": ["V", "I"],
    },
    {
        "project": "pubpub",
        "platform": "community",
        "relevance": "PubPub (Knowledge Futures) — open, community-owned publishing",
        "url": "https://pubpub.org",
        "tags": ["open-access", "publishing", "knowledge-futures"],
        "organs": ["V"],
    },
    # ── ORGAN-VI: Koinonia ───────────────────────────────────────────────
    {
        "project": "exercism",
        "platform": "community",
        "relevance": "Exercism — free, mentored coding practice across languages",
        "url": "https://exercism.org",
        "tags": ["education", "mentorship", "open-source"],
        "organs": ["VI"],
    },
    {
        "project": "the-odin-project",
        "platform": "community",
        "relevance": "The Odin Project — open-source full-stack curriculum and community",
        "url": "https://theodinproject.com",
        "tags": ["education", "open-source", "web-development"],
        "organs": ["VI"],
    },
    {
        "project": "hack-club",
        "platform": "community",
        "relevance": "Hack Club — global network of teen makers and coding clubs",
        "url": "https://hackclub.com",
        "tags": ["education", "makers", "youth"],
        "organs": ["VI", "II"],
    },
    # ── ORGAN-VII: Kerygma ───────────────────────────────────────────────
    {
        "project": "matrix-community",
        "platform": "community",
        "relevance": "Matrix — open standard for decentralized, federated communication",
        "url": "https://matrix.org",
        "tags": ["decentralization", "federation", "messaging"],
        "organs": ["VII"],
    },
    {
        "project": "nostr-community",
        "platform": "community",
        "relevance": "Nostr — simple, censorship-resistant decentralized social protocol",
        "url": "https://nostr.com",
        "tags": ["decentralization", "social-web", "protocol"],
        "organs": ["VII"],
    },
    # ── META / Governance ────────────────────────────────────────────────
    {
        "project": "all-contributors",
        "platform": "community",
        "relevance": "All Contributors — recognizing every kind of project contribution",
        "url": "https://allcontributors.org",
        "tags": ["recognition", "contributors", "governance"],
        "organs": ["META"],
    },
    {
        "project": "software-freedom-conservancy",
        "platform": "community",
        "relevance": "Software Freedom Conservancy — fiscal-sponsor home for FOSS projects",
        "url": "https://sfconservancy.org",
        "tags": ["open-source", "governance", "nonprofit"],
        "organs": ["META"],
    },
    {
        "project": "apache-software-foundation",
        "platform": "community",
        "relevance": "Apache Software Foundation — 'the Apache Way' of community governance",
        "url": "https://apache.org",
        "tags": ["open-source", "governance", "meritocracy"],
        "organs": ["META", "IV"],
    },
]


def suggest_parallel_mirrors(
    repo_tags: list[str],
    repo_description: str = "",
    existing_projects: set[str] | None = None,
) -> list[MirrorEntry]:
    """Suggest parallel mirror entries based on repo tags and description.

    Matches repo tags against PARALLEL_PROJECTS domain keys.
    Returns suggestions excluding already-mapped projects.
    """
    skip = existing_projects or set()
    suggestions: list[MirrorEntry] = []
    seen: set[str] = set()

    # Normalize tags for matching
    normalized_tags = {t.lower().replace("_", "-") for t in repo_tags}

    for domain, projects in PARALLEL_PROJECTS.items():
        # Check if any tag matches the domain key or its components
        domain_parts = set(domain.split("-"))
        if normalized_tags & domain_parts or domain in normalized_tags:
            for proj in projects:
                if proj["project"] not in skip and proj["project"] not in seen:
                    seen.add(proj["project"])
                    suggestions.append(MirrorEntry(
                        project=proj["project"],
                        platform="github",
                        relevance=proj["relevance"],
                        engagement=["presence", "dialogue"],
                        tags=["suggested", "parallel", domain],
                    ))

    # Also check description for domain keywords
    if repo_description:
        desc_lower = repo_description.lower()
        for domain, projects in PARALLEL_PROJECTS.items():
            if domain.replace("-", " ") in desc_lower:
                for proj in projects:
                    if proj["project"] not in skip and proj["project"] not in seen:
                        seen.add(proj["project"])
                        suggestions.append(MirrorEntry(
                            project=proj["project"],
                            platform="github",
                            relevance=proj["relevance"],
                            engagement=["presence", "dialogue"],
                            tags=["suggested", "parallel", domain],
                        ))

    return suggestions


def suggest_kinship_mirrors(
    repo_tags: list[str],
    organ: str = "",
    existing_projects: set[str] | None = None,
) -> list[MirrorEntry]:
    """Suggest kinship mirror entries based on repo and organ context.

    Matches against curated KINSHIP_COMMUNITIES list.
    These are SUGGESTIONS — human confirms before writing.
    """
    skip = existing_projects or set()
    suggestions: list[MirrorEntry] = []

    # Tag-based matching
    normalized_tags = {t.lower().replace("_", "-") for t in repo_tags}

    for community in KINSHIP_COMMUNITIES:
        if community["project"] in skip:
            continue
        comm_tags = set(community.get("tags", []))
        if comm_tags & normalized_tags:
            suggestions.append(MirrorEntry(
                project=community["project"],
                platform=community.get("platform", "community"),
                relevance=community["relevance"],
                engagement=["presence", "dialogue"],
                url=community.get("url"),
                tags=["suggested", "kinship"] + community.get("tags", []),
            ))

    # Organ-based suggestions (always relevant for certain organs)
    organ_upper = organ.upper()
    if organ_upper in ("ORGAN-I", "META") and "tools-for-thought" not in skip:
        suggestions.append(MirrorEntry(
            project="tools-for-thought",
            platform="community",
            relevance="Knowledge management alignment with ORGAN-I theory work",
            engagement=["presence", "dialogue"],
            tags=["suggested", "kinship", "knowledge-management"],
        ))
    if organ_upper == "ORGAN-II":
        for comm in KINSHIP_COMMUNITIES:
            if (
                any(t in comm.get("tags", []) for t in ("creative-coding", "art-tech"))
                and comm["project"] not in skip
            ):
                    suggestions.append(MirrorEntry(
                        project=comm["project"],
                        platform=comm.get("platform", "community"),
                        relevance=comm["relevance"],
                        engagement=["presence", "dialogue"],
                        url=comm.get("url"),
                        tags=["suggested", "kinship", "organ-ii"],
                    ))

    # Deduplicate by project
    seen: set[str] = set()
    unique: list[MirrorEntry] = []
    for s in suggestions:
        if s.project not in seen:
            seen.add(s.project)
            unique.append(s)

    return unique
