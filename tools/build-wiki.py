#!/usr/bin/env python3
"""
build-wiki.py — render the GitHub wiki into public/wiki/ as static pages.

⚠ THIS RUNS ON THE AUTHOR'S MACHINE, NEVER AT DEPLOY TIME. Cloudflare serves
public/ with no build command (see wrangler.jsonc), and that is the property
worth keeping: the thing that is deployed is the thing that is in the repo, and
it can be read, diffed and reverted. So this script writes HTML into public/
and the HTML is committed. `--check` re-renders into a temp directory and
diffs, which is what CI would run if it ever grew one.

⚠ THE WIKI IS THE SOURCE, THIS IS A MIRROR. Editing public/wiki/*.html by hand
puts the site and the wiki into disagreement with no warning — the next run
silently reverts it. Every generated page carries an "Edit on GitHub" link for
exactly that reason, and every page says at the bottom where it came from.

⛔ NO JAVASCRIPT, EVER. _headers sets `script-src 'none'`, so anything that
needs script is not an option here — no client-side search, no syntax
highlighter, no collapsible nav that toggles a class. Everything below is
resolved at build time or done in CSS. `style-src 'self'` also means an inline
`style=` attribute is refused SILENTLY, so this emits classes only.

Usage:
    tools/build-wiki.py                 # clone the published wiki, render it
    tools/build-wiki.py --wiki ../SYNAPSE.wiki
    tools/build-wiki.py --check         # render to a temp dir, diff, exit 1 on drift

Needs python-markdown and pygments (Arch: python-markdown python-pygments).
"""
from __future__ import annotations

import argparse
import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import markdown
except ImportError:
    sys.exit("build-wiki: python-markdown is not installed (pacman -S python-markdown)")

REPO      = Path(__file__).resolve().parent.parent
PUBLIC    = REPO / "public"
OUT       = PUBLIC / "wiki"
WIKI_URL  = "https://github.com/velle999/SYNAPSE.wiki.git"
GH_WIKI   = "https://github.com/velle999/SYNAPSE/wiki"
SITE      = "https://soslinux.org"

# ⚠ BUMPED BY HAND WHEN THE CSS CHANGES. /assets/* is immutable for a year in
# _headers, so an edit at an unversioned URL never reaches anyone who has
# already visited. Same convention as style.css's ?v= in index.html.
STYLE_V   = "2026-08-25"
WIKI_V    = "2026-08-29"


# ── the wiki source ─────────────────────────────────────────────────────────

def wiki_tree(given: str | None) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """A path to a wiki checkout, cloning the published one if none was given.

    ⚠ CLONING IS THE DEFAULT ON PURPOSE. The site should mirror what is
    PUBLISHED, not what happens to be sitting in somebody's working tree — a
    half-finished page rendered onto soslinux.org is worse than a stale one.
    """
    if given:
        p = Path(given).expanduser().resolve()
        if not (p / "Home.md").is_file():
            sys.exit(f"build-wiki: {p} does not look like the wiki (no Home.md)")
        return p, None

    tmp = tempfile.TemporaryDirectory(prefix="synapse-wiki-")
    dest = Path(tmp.name) / "wiki"
    print(f"  cloning {WIKI_URL}")
    # ⛔ NOT A SHALLOW CLONE. Every page carries the date of its last edit, and
    # `git log -1 -- <file>` in a truncated history answers with the shallow
    # boundary — or with nothing at all for a page nobody has touched lately.
    # It exits 0 either way, so the wrong date ships quietly. The whole wiki is
    # a few hundred kilobytes; there is nothing to save here.
    r = subprocess.run(["git", "clone", "--quiet", WIKI_URL, str(dest)])
    if r.returncode != 0:
        sys.exit("build-wiki: clone failed — pass --wiki <path> to use a local checkout")
    return dest, tmp


def last_touched(tree: Path, name: str) -> str:
    """The page's last commit date, or "" when git cannot say."""
    r = subprocess.run(["git", "-C", str(tree), "log", "-1", "--format=%cs", "--", name],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


# ── the sidebar is the table of contents, the order and the sections ────────

SIDE_LINK = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)\s*$")
SIDE_HEAD = re.compile(r"^\*\*(.+?)\*\*\s*$")


def parse_sidebar(md: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """_Sidebar.md → [(group, [(label, page), …]), …].

    ⚠ THE WIKI'S OWN SIDEBAR IS THE ONLY ORDERING THAT EXISTS. Deriving one
    here — alphabetical, or by filename — would give the site a running order
    that disagrees with the wiki's, and prev/next links that lead somewhere
    different depending on which copy you are reading.
    """
    groups: list[tuple[str, list[tuple[str, str]]]] = []
    current: list[tuple[str, str]] = []
    title = ""
    for line in md.splitlines():
        h = SIDE_HEAD.match(line)
        if h:
            if title and current:
                groups.append((title, current))
            title, current = h.group(1), []
            continue
        m = SIDE_LINK.match(line)
        if m and title:
            target = m.group(2).split("#")[0]
            if not target.startswith("http"):
                current.append((m.group(1), target))
    if title and current:
        groups.append((title, current))
    return groups


# ── slugs ───────────────────────────────────────────────────────────────────

# ⛔ GITHUB'S ALGORITHM, NOT python-markdown's. Every `[x](Page#anchor)` in the
# wiki was written against GitHub's slugs; python-markdown's own slugify drops
# different characters, so using it would silently break 36 in-page links —
# silently, because a fragment that matches nothing is not an error, it just
# leaves you at the top of the page.
#
# GitHub: lowercase, strip everything that is not a letter, digit, space,
# hyphen or underscore, then spaces to hyphens. Duplicates get -1, -2, …
_SLUG_STRIP = re.compile(r"[^\w\- ]", re.UNICODE)


def gh_slug(text: str, sep: str = "-") -> str:
    s = html.unescape(text).strip().lower()
    s = _SLUG_STRIP.sub("", s)
    return s.replace(" ", sep)


class SlugCounter:
    """GitHub's duplicate suffixes, per page."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}

    def __call__(self, text: str, sep: str = "-") -> str:
        base = gh_slug(text, sep)
        n = self.seen.get(base, 0)
        self.seen[base] = n + 1
        return base if n == 0 else f"{base}-{n}"


# ── markdown → html ─────────────────────────────────────────────────────────

DETAILS_OPEN = re.compile(r"^<details>\s*$", re.M)


def convert(md_text: str, pages: set[str]) -> tuple[str, list[tuple[int, str, str]]]:
    """Returns (html, [(level, id, text), …]) for the page's headings."""

    # `md_in_html` only descends into an element that ASKS for it. GitHub
    # processes markdown inside <details> without being told, so a block that
    # renders on the wiki would come out as literal asterisks here.
    md_text = DETAILS_OPEN.sub('<details markdown="1">', md_text)

    slugger = SlugCounter()
    md = markdown.Markdown(
        extensions=["extra", "sane_lists", "toc", "codehilite", "md_in_html"],
        extension_configs={
            "toc": {"slugify": slugger, "anchorlink": False, "permalink": False},
            # ⚠ guess_lang OFF. An unlabelled ``` fence is usually console
            # OUTPUT here, and a guesser confidently paints it as some
            # language, which is worse than leaving it plain.
            "codehilite": {"guess_lang": False, "css_class": "hl", "linenums": False},
        },
    )
    body = md.convert(md_text)
    toc = [(int(t["level"]), t["id"], t["name"]) for t in md.toc_tokens_flat()] \
        if hasattr(md, "toc_tokens_flat") else _flatten_toc(md.toc_tokens)
    return body, toc


def _flatten_toc(tokens) -> list[tuple[int, str, str]]:
    out: list[tuple[int, str, str]] = []

    def walk(ts):
        for t in ts:
            out.append((t["level"], t["id"], t["name"]))
            walk(t.get("children", []))

    walk(tokens)
    return out


# ── link rewriting ──────────────────────────────────────────────────────────

HREF = re.compile(r'href="([^"]+)"')


def rewrite_links(body: str, pages: set[str], src: str, problems: list[str]) -> str:
    """`[x](Page)` → /wiki/Page, and shout about anything that resolves nowhere.

    ⚠ A BROKEN LINK IS A BUILD FAILURE, not a 404 for a reader to find. The
    wiki's own links work on GitHub because GitHub resolves a bare page name;
    nothing does that here, so every one of them has to be rewritten and every
    one that cannot be is a page that was renamed without its referrers.
    """

    def fix(m: re.Match) -> str:
        href = html.unescape(m.group(1))
        if href.startswith(("http://", "https://", "mailto:", "#", "/")):
            return m.group(0)
        page, _, frag = href.partition("#")
        if not page:
            return m.group(0)
        if page not in pages:
            problems.append(f"{src}: link to '{page}', which is not a wiki page")
            return m.group(0)
        target = "/wiki/" if page == "Home" else f"/wiki/{page}"
        return f'href="{html.escape(target + ("#" + frag if frag else ""), quote=True)}"'

    return HREF.sub(fix, body)


# ⚠ EVERY TABLE GETS A SCROLL BOX. style.css sets `table { min-width: 32rem }`
# because a table narrower than that stops being readable — which means a table
# in a phone-width column overflows the PAGE unless something clips it. The
# homepage wraps its own tables by hand; markdown emits a bare <table>, so the
# wrapper has to be put back here.
TABLE = re.compile(r"<table>(.*?)</table>", re.S)


def wrap_tables(body: str) -> str:
    # ⚠ AND `\|` BECOMES `|`, INSIDE THE TABLE ONLY. A pipe in a table cell has
    # to be written escaped or it ends the cell, and GitHub unescapes it on the
    # way out — python-markdown does not when the cell is a code span, so
    # `vibe wake on\|off` ships the backslash and reads as part of the command.
    # Scoped to <table> because a `\|` inside a fenced block is sed, and real.
    return TABLE.sub(
        lambda m: '<div class="table-scroll"><table>'
                  + m.group(1).replace("\\|", "|") + "</table></div>",
        body)


# ⚠ A CALLOUT IS RECOGNISED BY ITS OWN FIRST CHARACTERS. The wiki writes
# warnings as `> ⚠ …` and prohibitions as `> ⛔ …`, so the marker is already in
# the text and does not need a second syntax invented for it here.
BQ = re.compile(r"<blockquote>\s*(<p>(?:<[^>]+>)*\s*([⚠⛔]))")


def mark_callouts(body: str) -> str:
    return BQ.sub(lambda m: f'<blockquote class="warn">{m.group(1)}', body)


# ── the page shell ──────────────────────────────────────────────────────────

def nav_html(current: str, groups) -> str:
    out = ['<nav class="wiki-side" aria-label="All wiki pages">',
           '<p class="wiki-side-top"><a href="/wiki/">SynapseOS Wiki</a></p>']
    for title, items in groups:
        out.append(f"<p class=\"wiki-side-h\">{html.escape(title)}</p><ul>")
        for label, page in items:
            href = "/wiki/" if page == "Home" else f"/wiki/{page}"
            cur = ' aria-current="page"' if page == current else ""
            out.append(f'<li><a href="{href}"{cur}>{html.escape(label)}</a></li>')
        out.append("</ul>")
    out.append('<p class="wiki-side-foot">'
               f'<a href="{GH_WIKI}" rel="noopener">Edit on GitHub</a></p>')
    out.append("</nav>")
    return "\n".join(out)


def toc_html(toc: list[tuple[int, str, str]]) -> str:
    """h2 and h3 only. h4 makes the rail longer than the page it indexes."""
    items = [t for t in toc if t[0] in (2, 3)]
    if len(items) < 3:
        return ""
    # ⚠ A CHECKBOX AND A LABEL, which is how the homepage's theme switcher and
    # its screenshot carousel already work — `script-src 'none'` leaves no other
    # way to collapse something. NOT a <details>: the UA sheet hides its content
    # in a way author CSS cannot reliably re-show at a wide width, which would
    # ship a nav that some readers cannot open and no script to rescue it.
    #
    # On a wide screen the checkbox and label are hidden and the list is simply
    # there; on a phone the list is behind the label, because a 30-item contents
    # ahead of the article is not a table of contents, it is a wall.
    out = ['<nav class="wiki-toc" aria-label="On this page">',
           '<input class="toc-toggle" type="checkbox" id="toc-open">',
           '<label class="toc-label" for="toc-open">On this page</label>',
           '<p class="wiki-toc-h">On this page</p><ul>']
    for level, anchor, text in items:
        cls = ' class="sub"' if level == 3 else ""
        out.append(f'<li{cls}><a href="#{html.escape(anchor, quote=True)}">'
                   f"{html.escape(text)}</a></li>")
    out.append("</ul></nav>")
    return "\n".join(out)


# ⚠ THE SAME ROW AS THE HOMEPAGE, IN THE SAME ORDER. A header that quietly
# loses an item when you follow a link reads as a different site — so Merch is
# here despite being of no use on a wiki page, and Wiki is on the homepage.
# Changing one means changing the other; there is no shared template to hold
# them together, because there is no build step at deploy time.
HEADER_NAV = [
    ("/#what", "What it is"), ("/#desktop", "Desktop"), ("/#gallery", "Screenshots"),
    ("/#components", "Components"), ("/wiki/", "Wiki"), ("/#download", "Download"),
    ("/#merch", "Merch"), ("https://github.com/velle999/SYNAPSE", "GitHub"),
]


def shell(*, title: str, desc: str, canonical: str, body: str) -> str:
    nav = "\n      ".join(
        f'<a href="{h}"{" rel=\"noopener\"" if h.startswith("http") else ""}'
        f'{" aria-current=\"page\"" if h == "/wiki/" else ""}>{t}</a>'
        for h, t in HEADER_NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc, quote=True)}">
<link rel="canonical" href="{canonical}">
<meta name="robots" content="index, follow, max-snippet:-1">
<meta name="author" content="Velle Sinclair">
<meta name="theme-color" content="#0a0a12">
<meta name="color-scheme" content="dark">

<meta property="og:type" content="article">
<meta property="og:site_name" content="SynapseOS Wiki">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(desc, quote=True)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/assets/og.png?v=2026-08-22">
<meta name="twitter:card" content="summary_large_image">

<link rel="icon" href="/assets/logo.svg" type="image/svg+xml" media="(prefers-color-scheme: dark)">
<link rel="icon" href="/assets/logo-ink.svg" type="image/svg+xml" media="(prefers-color-scheme: light)">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="stylesheet" href="/assets/style.css?v={STYLE_V}">
<link rel="stylesheet" href="/assets/wiki.css?v={WIKI_V}">
</head>
<body>

<div class="page">
<a class="skip" href="#main">Skip to content</a>

<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="/">
      <img src="/assets/logo.svg" alt="" width="34" height="34" decoding="async">
      <span>SynapseOS</span>
    </a>
    <nav aria-label="Primary">
      {nav}
    </nav>
  </div>
</header>

{body}

<footer class="site-footer">
  <div class="wrap">
    <p>
      <strong>SynapseOS</strong> &mdash; where the kernel thinks.
      Built by <a href="https://github.com/velle999" rel="noopener">Velle Sinclair</a>.
    </p>
    <p class="small">
      These pages are rendered from the
      <a href="{GH_WIKI}" rel="noopener">project wiki</a>, which is where they are
      edited. GPL-2.0-or-later. Not affiliated with or endorsed by Arch Linux.
    </p>
  </div>
</footer>

</div><!-- /.page -->
</body>
</html>
"""


def first_paragraph(md_text: str) -> str:
    """A description for the <meta> tag: the page's own opening sentence.

    ⚠ THIS IS THE SEARCH RESULT. A page whose intro is a caution — Installation
    opens with one — has no ordinary paragraph until well down the file, so a
    plain "first paragraph" reader returns the horizontal rule underneath it and
    Google shows three dashes. Prose is preferred and a blockquote is the
    fallback, rather than either being the only thing looked at.
    """
    plain = _lead(md_text, quotes=False)
    return _tidy(plain or _lead(md_text, quotes=True)) or \
        "The SynapseOS operator's manual."


RULE = re.compile(r"^([-*_])\1{2,}$")


def _lead(md_text: str, *, quotes: bool) -> str:
    # ⛔ A HEADING ENDS THE SEARCH. Prose after `## Try it in QEMU first` is
    # about QEMU, not about the page — taking it gives Installation a
    # description that opens "Uses KVM when available", which is true of
    # something on the page and wrong about the page.
    buf: list[str] = []
    fence = False
    for ln in md_text.splitlines()[1:]:
        s = ln.strip()
        if s.startswith("```"):
            fence = not fence
            if buf:
                break
            continue
        if fence or RULE.match(s):
            continue
        if s.startswith("#"):
            break
        if not s:
            # One short line — a bold standfirst, which several pages open
            # with — is not a description. Keep reading into the paragraph
            # under it and stop once there is enough to be a sentence.
            if len(" ".join(buf)) >= 80:
                break
            continue
        if s.startswith(">"):
            if not quotes:
                continue
            s = s.lstrip("> ").strip()
            if not s:
                continue
        elif s.startswith(("|", "<", "- ", "* ", "-\t", "*\t")):
            # A list marker is "- " WITH the space; testing the bare character
            # throws away every paragraph that opens in bold, which is how most
            # pages here open.
            if buf:
                break
            continue
        buf.append(s)
    return " ".join(buf)


def _tidy(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text).replace("*", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 180:
        text = text[:177].rsplit(" ", 1)[0] + "\u2026"
    return text


# ── build ───────────────────────────────────────────────────────────────────

def build(tree: Path, out: Path) -> int:
    sidebar = parse_sidebar((tree / "_Sidebar.md").read_text(encoding="utf-8"))
    order: list[str] = []
    section_of: dict[str, str] = {}
    label_of: dict[str, str] = {}
    for group, items in sidebar:
        for label, page in items:
            if page not in section_of:
                order.append(page)
                section_of[page] = group
                label_of[page] = label

    sources = sorted(p for p in tree.glob("*.md") if p.name != "_Sidebar.md")
    pages = {p.stem for p in sources}

    missing = [p for p in order if p not in pages]
    if missing:
        sys.exit(f"build-wiki: the sidebar names pages that do not exist: {missing}")
    # Home is the rail's masthead link, not one of its groups.
    unlisted = sorted(pages - set(order) - {"Home"})
    if unlisted:
        print(f"  note: not in the sidebar, rendered but unreachable from the nav: "
              f"{', '.join(unlisted)}")

    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.html"):
        stale.unlink()

    problems: list[str] = []
    anchors: dict[str, set[str]] = {}
    written: list[tuple[str, str]] = []
    edited: dict[str, str] = {}

    for src in sources:
        page = src.stem
        md_text = src.read_text(encoding="utf-8")

        # The h1 on line 1 becomes the page's masthead, so it must not also be
        # the first thing in the body.
        lines = md_text.splitlines()
        h1 = lines[0][2:].strip() if lines and lines[0].startswith("# ") else page
        rest = "\n".join(lines[1:]).lstrip("\n")

        body_html, toc = convert(rest, pages)
        body_html = rewrite_links(body_html, pages, src.name, problems)
        body_html = mark_callouts(wrap_tables(body_html))
        anchors[page] = {a for _, a, _ in toc}

        i = order.index(page) if page in order else -1
        prev_p = order[i - 1] if i > 0 else None
        next_p = order[i + 1] if 0 <= i < len(order) - 1 else None

        pager = []
        if prev_p:
            pager.append(f'<a class="prev" href="/wiki/{prev_p}">'
                         f'<span>Previous</span>{html.escape(label_of[prev_p])}</a>')
        if next_p:
            pager.append(f'<a class="next" href="/wiki/{next_p}">'
                         f'<span>Next</span>{html.escape(label_of[next_p])}</a>')
        pager_html = f'<nav class="wiki-pager" aria-label="Nearby pages">{"".join(pager)}</nav>' \
            if pager else ""

        touched = last_touched(tree, src.name)
        edited[page] = touched
        stamp = f' &middot; last edited <time datetime="{touched}">{touched}</time>' \
            if touched else ""
        eyebrow = section_of.get(page, "Wiki")

        is_home = page == "Home"
        canonical = f"{SITE}/wiki/" if is_home else f"{SITE}/wiki/{page}"
        edit = f"{GH_WIKI}/{page}/_edit"

        main = f"""<main id="main" class="wiki">
  <div class="wiki-wrap wiki-layout">

{toc_html(toc)}

    <article class="wiki-main">
      <p class="eyebrow">{html.escape(eyebrow)}</p>
      <h1>{html.escape(h1)}</h1>
      <p class="wiki-meta">
        <a href="{edit}" rel="noopener">Edit on GitHub</a>{stamp}
      </p>

      <div class="wiki-body">
{body_html}
      </div>

{pager_html}
    </article>

{nav_html(page, sidebar)}

  </div>
</main>"""

        title = "SynapseOS Wiki" if is_home else f"{h1} &mdash; SynapseOS Wiki"
        html_out = shell(title=html.unescape(title), desc=first_paragraph(md_text),
                         canonical=canonical, body=main)
        name = "index.html" if is_home else f"{page}.html"
        (out / name).write_text(html_out, encoding="utf-8")
        written.append((page, name))

    # ⚠ ANCHORS ARE CHECKED AFTER EVERY PAGE HAS BEEN SEEN, because a link may
    # point forward. A fragment that matches nothing lands the reader at the top
    # of the right page with no sign anything went wrong, which is exactly the
    # class of silent failure this project keeps writing down.
    for src in sources:
        text = src.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]\n]+\]\(([^)\s]+)\)", text):
            href = m.group(1)
            if href.startswith(("http", "mailto:")):
                continue
            page, _, frag = href.partition("#")
            page = page or src.stem
            if not frag or page not in anchors:
                continue
            if frag not in anchors[page]:
                problems.append(f"{src.name}: '#{frag}' is not a heading on {page}")

    if problems:
        print("\nbuild-wiki: unresolved links\n")
        for p in problems:
            print(f"  {p}")
        return 1

    where = out.relative_to(REPO) if out.is_relative_to(REPO) else out
    print(f"  {len(written)} pages → {where}")
    DATES.update(edited)
    return 0


# The per-page edit dates the last build() saw, for the sitemap.
DATES: dict[str, str] = {}


def write_sitemap(tree: Path) -> None:
    """One <url> per wiki page, so they are indexed rather than merely reachable.

    ⚠ EACH PAGE'S OWN LAST-EDIT DATE, not today's. Stamping the whole wiki with
    the build date tells a crawler that thirty-eight pages changed every time
    one of them did, which is how a sitemap stops being believed.
    """
    pages = sorted(p.stem for p in tree.glob("*.md") if p.name != "_Sidebar.md")
    today = datetime.date.today().isoformat()
    urls = [f"""  <url>
    <loc>{SITE}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{SITE}/wiki/</loc>
    <lastmod>{DATES.get("Home") or today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>"""]
    for p in pages:
        if p == "Home":
            continue
        urls.append(f"""  <url>
    <loc>{SITE}/wiki/{p}</loc>
    <lastmod>{DATES.get(p) or today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    body = "\n".join(urls)
    (PUBLIC / "sitemap.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by tools/build-wiki.py — the wiki entries are one per page. -->
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
""", encoding="utf-8")
    print(f"  sitemap: {len(pages) + 1} urls")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wiki", help="path to a wiki checkout (default: clone the published one)")
    ap.add_argument("--check", action="store_true",
                    help="render to a temp dir and diff against public/wiki")
    args = ap.parse_args()

    print("build-wiki")
    tree, tmp = wiki_tree(args.wiki)
    try:
        if args.check:
            with tempfile.TemporaryDirectory() as td:
                rc = build(tree, Path(td))
                if rc:
                    return rc
                d = subprocess.run(["diff", "-r", "-q", str(OUT), td],
                                   capture_output=True, text=True)
                if d.returncode != 0:
                    print("\nbuild-wiki: public/wiki is out of date:\n")
                    print(d.stdout)
                    return 1
                print("  public/wiki matches the wiki")
                return 0

        rc = build(tree, OUT)
        if rc:
            return rc
        write_sitemap(tree)
        return 0
    finally:
        if tmp:
            tmp.cleanup()


if __name__ == "__main__":
    sys.exit(main())
