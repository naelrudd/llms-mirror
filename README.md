# llms-mirror

[![PyPI version](https://img.shields.io/pypi/v/llms-mirror)](https://pypi.org/project/llms-mirror/)
[![PyPI downloads](https://img.shields.io/pypi/dm/llms-mirror)](https://pypi.org/project/llms-mirror/)

Mirror an official documentation site (via its [`llms.txt`](https://llmstxt.org) index) as plain Markdown, organized 1:1 by URL path, ready for LLM ingestion, RAG pipelines, and knowledge graphs.

Pure standard library for Markdown sites — no dependencies. Optional `html2text` extra for HTML-only sites. Mirrors Midtrans, Clerk, Canva, Xendit, Stripe, and Razorpay docs with one command.

## Install

```bash
pip install llms-mirror          # Markdown sites (no deps)
pip install "llms-mirror[html]"  # HTML-only sites
```

## Usage

```bash
# Full pipeline: crawl site -> Markdown tree -> llms-full.txt + README + INDEX
llms-mirror mirror https://stripe.com/docs/llms.txt --out stripe-docs

# From an already-mirrored directory, rebuild artifacts
llms-mirror full                # regenerate llms-full.txt
llms-mirror index               # regenerate README.md + INDEX.md
```

Options:

| Flag | Meaning |
|---|---|
| `--out DIR` | output directory (default `docs`) |
| `--workers N` | parallel downloads (default 8) |
| `--retries N` | retries per page on transient errors (default 3) |
| `--delay SEC` | min seconds between requests (rate-limit friendly) |
| `--redact` | replace Stripe-style API keys (`sk_test_...`) and AWS keys with `REPLACE_ME` |
| `--html` | pages are HTML; convert to Markdown (needs `llms-mirror[html]`) |
| `--strip-fm` | strip YAML frontmatter from pages |
| `--no-llms-full` | skip the single-file corpus |
| `--local-index` | reuse saved `llms.txt` instead of re-fetching (resume during throttling) |
| `--no-git` | skip `git init` + commit |

## Output

```
docs/
├── llms.txt          # original official index (verbatim)
├── llms-full.txt     # entire corpus in one file
├── INDEX.md          # every page + first heading
├── README.md         # landing page
├── missing.md        # pages that failed to download (404 etc.)
└── <path>/.../*.md   # mirrored pages, URL structure preserved
```

## Examples

- https://github.com/naelrudd/midtrans-docs-llm-agents (589 pages)
- https://github.com/naelrudd/clerk-docs-llm-agents (2343 pages)
- https://github.com/naelrudd/xendit-docs-llm-agents (336 pages)
- https://github.com/naelrudd/stripe-docs-llm-agents (473 pages)
- https://github.com/naelrudd/canva-docs (392 pages)
- https://github.com/naelrudd/razorpay-docs-llm-agents

## License

MIT
