"""llms-mirror: mirror an official documentation site (via its llms.txt index)
as plain Markdown for LLM ingestion, RAG pipelines, and knowledge graphs.

Pure stdlib. One pipeline: mirror a site, then (re)build single-file corpus
(llms-full.txt) and README/INDEX from a local corpus.
"""

import argparse
import concurrent.futures
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

__version__ = "0.1.0"

USER_AGENT = "llms-mirror/0.1.0 (+https://github.com/naelrudd/llms-mirror)"
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
KEY_RE = re.compile(r"\b((?:sk|pk|rk)_(?:test|live|prod)_)[A-Za-z0-9]{16,}\b")
SKIP_FILES = {"README.md", "INDEX.md", "llms.txt", "llms-full.txt", "missing.md"}


# ---------------------------------------------------------------- network

def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_text(url: str, timeout: int = 30) -> str:
    data = fetch_bytes(url, timeout=timeout)
    text = data.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


# ---------------------------------------------------------------- parsing

def parse_links(text: str, base_url: str) -> list[str]:
    links = []
    for m in LINK_RE.finditer(text):
        raw = m.group(1).strip()
        if raw.startswith(("http://", "https://")):
            abs_url = raw
        else:
            abs_url = urllib.parse.urljoin(base_url, raw)
        links.append(abs_url)
    return links


def doc_links(links: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for u in links:
        if "#" in urllib.parse.urlsplit(u).fragment or not u.rstrip("/").endswith(".md"):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------------------------------------------------------------- filesystem

def safe_path(url: str) -> Path:
    """URL -> repo-relative path preserving the URL structure."""
    path = urllib.parse.urlsplit(url).path.strip("/")
    if not path:
        path = "index.md"
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    return Path(*parts)


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def redact_keys(text: str) -> str:
    return KEY_RE.sub(r"\1REPLACE_ME", text)


# ---------------------------------------------------------------- crawling

def download_all(
    urls: list[str],
    outdir: Path,
    workers: int = 8,
    timeout: int = 30,
    redact: bool = False,
    strip_fm: bool = False,
) -> list[str]:
    outdir.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []

    def one(url: str) -> tuple[str, bool]:
        rel = safe_path(url)
        dest = outdir / rel
        try:
            text = fetch_text(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            return (url, e.code != 404)
        except Exception:
            return (url, True)
        if strip_fm:
            text = strip_frontmatter(text)
        if redact:
            text = redact_keys(text)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return (url, True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for url, ok in ex.map(one, urls):
            if not ok:
                missing.append(url)
    return missing


# ---------------------------------------------------------------- artifacts

def title_for(url: str) -> str:
    host = urllib.parse.urlsplit(url).netloc
    return host.replace("www.", "").split(".")[0].title()


def first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def build_llms_full(outdir: Path, llms_url: str, out_name: str = "llms-full.txt") -> Path:
    pages = sorted(
        (outdir / p)
        for p in outdir.rglob("*.md")
        if p.is_file() and p.name not in SKIP_FILES
    )
    sep = "=" * 72
    lines = [
        f"# {title_for(llms_url)} — Full corpus (single-file)",
        f"Source: {llms_url}",
        f"Pages: {len(pages)}",
        "",
    ]
    for page in pages:
        rel = page.relative_to(outdir).as_posix()
        lines += [sep, "", f"# {rel}", "", sep, "", page.read_text(encoding="utf-8").strip(), ""]
    dest = outdir / out_name
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def build_index(outdir: Path, llms_url: str) -> Path:
    pages = sorted(
        (outdir / p)
        for p in outdir.rglob("*.md")
        if p.is_file() and p.name not in SKIP_FILES
    )
    root = urllib.parse.urlsplit(llms_url)
    base = f"{root.scheme}://{root.netloc}"
    rows = []
    for page in pages:
        rel = page.relative_to(outdir).as_posix()
        text = page.read_text(encoding="utf-8", errors="replace")
        heading = first_heading(text)
        rows.append(f"| [{rel}]({base}/{rel}) | {heading} |")
    lines = [
        f"# Index — {title_for(llms_url)}",
        f"Source: {llms_url}",
        f"Pages: {len(pages)}",
        "",
        "| Path | First heading |",
        "|---|---|",
        *rows,
        "",
    ]
    dest = outdir / "INDEX.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def build_readme(outdir: Path, llms_url: str) -> Path:
    pages = sum(
        1
        for p in outdir.rglob("*.md")
        if p.is_file() and p.name not in SKIP_FILES
    )
    lines = [
        f"# {title_for(llms_url)} docs — LLM mirror",
        "",
        f"Machine-readable mirror of [official docs]({llms_url}) as plain Markdown, "
        "organized 1:1 by URL path, for LLM ingestion, RAG, and knowledge graphs.",
        "",
        "## Quick start",
        "",
        "- `llms.txt` — official link index",
        f"- `llms-full.txt` — entire corpus in one file ({pages} pages)",
        "- `INDEX.md` — every page with its first heading",
        "",
        "Point an LLM at `llms-full.txt`, or feed `INDEX.md` for discovery.",
        "",
        "## Rebuild from local corpus",
        "",
        "```bash",
        "llms-mirror full   # regenerate llms-full.txt",
        "llms-mirror index  # regenerate README.md / INDEX.md",
        "```",
        "",
    ]
    dest = outdir / "README.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def write_missing(outdir: Path, missing: list[str]) -> None:
    outdir.joinpath("missing.md").write_text(
        "\n".join(["# Failed downloads", ""] + missing + [""]), encoding="utf-8"
    )


# ---------------------------------------------------------------- git

def git_init(outdir: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-b", "main"], cwd=outdir, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=outdir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "Mirror docs as Markdown (llms-mirror)"],
        cwd=outdir,
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------- CLI

def cmd_mirror(args: argparse.Namespace) -> int:
    outdir = Path(args.out)
    print(f"Fetching {args.llms_url} ...")
    try:
        text = fetch_text(args.llms_url, timeout=args.timeout)
    except Exception as e:
        print(f"ERROR: cannot fetch {args.llms_url}: {e}", file=sys.stderr)
        return 1

    links = doc_links(parse_links(text, args.llms_url))
    if not links:
        print("ERROR: no .md links found in llms.txt", file=sys.stderr)
        return 1
    print(f"Found {len(links)} doc pages")

    outdir.mkdir(parents=True, exist_ok=True)
    outdir.joinpath(".llms-mirror").write_text(args.llms_url + "\n", encoding="utf-8")
    outdir.joinpath("llms.txt").write_text(text, encoding="utf-8")

    missing = download_all(links, outdir, args.workers, args.timeout, args.redact, args.strip_fm)
    if missing:
        write_missing(outdir, missing)
        print(f"NOTE: {len(missing)} pages failed -> missing.md")

    build_index(outdir, args.llms_url)
    if args.llmsfull:
        dest = build_llms_full(outdir, args.llms_url)
        print(f"llms-full.txt: {dest.stat().st_size / 1e6:.1f} MB")
    build_readme(outdir, args.llms_url)

    if not args.no_git:
        git_init(outdir)
    print(f"Done -> {outdir}")
    return 0


def cmd_full(args: argparse.Namespace) -> int:
    outdir = Path(args.dir)
    llms_url = args.llms_url or _find_source(outdir)
    dest = build_llms_full(outdir, llms_url, args.out)
    print(f"{dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    outdir = Path(args.dir)
    llms_url = args.llms_url or _find_source(outdir)
    build_index(outdir, llms_url)
    build_readme(outdir, llms_url)
    print(f"Regenerated INDEX.md + README.md in {outdir}")
    return 0


def _find_source(outdir: Path) -> str:
    meta = outdir / ".llms-mirror"
    if meta.exists():
        url = meta.read_text(encoding="utf-8").strip()
        if url:
            return url
    txt = outdir / "llms.txt"
    if txt.exists():
        for m in re.finditer(r"https?://[^\s)]+llms\.txt", txt.read_text(encoding="utf-8", errors="replace")):
            return m.group(0)
    return "https://example.com/docs/llms.txt"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="llms-mirror",
        description="Mirror official docs (via llms.txt) as plain Markdown for LLMs.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("mirror", help="full pipeline: crawl site from llms.txt")
    m.add_argument("llms_url", help="URL of the site's llms.txt")
    m.add_argument("--out", default="docs", help="output directory (default: docs)")
    m.add_argument("--workers", type=int, default=8, help="parallel downloads")
    m.add_argument("--timeout", type=int, default=30, help="per-request timeout seconds")
    m.add_argument("--redact", action="store_true", help="redact Stripe-style API keys in page bodies")
    m.add_argument("--strip-fm", action="store_true", help="strip YAML frontmatter from pages")
    m.add_argument("--no-llms-full", dest="llmsfull", action="store_false", help="skip building llms-full.txt")
    m.add_argument("--no-git", action="store_true", help="skip git init/commit")
    m.set_defaults(func=cmd_mirror)

    f = sub.add_parser("full", help="regenerate llms-full.txt from a local corpus")
    f.add_argument("--dir", default=".", help="corpus directory (default: .)")
    f.add_argument("--out", default="llms-full.txt", help="output filename")
    f.add_argument("--llms-url", default=None, help="source llms.txt URL (auto-detected if omitted)")
    f.set_defaults(func=cmd_full)

    i = sub.add_parser("index", help="regenerate README.md + INDEX.md from a local corpus")
    i.add_argument("--dir", default=".", help="corpus directory (default: .)")
    i.add_argument("--llms-url", default=None, help="source llms.txt URL (auto-detected if omitted)")
    i.set_defaults(func=cmd_index)

    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
