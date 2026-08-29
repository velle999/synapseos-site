# synapseos-site

The public website for **[SynapseOS](https://github.com/velle999/SYNAPSE)** — an
Arch-based Linux distribution with a local LLM wired into the system layer.

It is a static site with no build step, no framework and no external requests —
every asset is served from this repo, which is also what the `Content-Security-Policy`
in `_headers` enforces.

```
wrangler.jsonc          Cloudflare Workers config — the entire deploy
public/                 EVERYTHING IN HERE IS PUBLIC. Nothing outside it is.
  index.html            the page (content, metadata, JSON-LD)
  404.html              not-found page
  robots.txt            crawl policy + sitemap pointer
  sitemap.xml           one URL; bump <lastmod> on a content change
  _headers              caching + security headers
  wiki/                 GENERATED — the project wiki, rendered. Never edit by
                        hand; see "The wiki" below.
  assets/style.css      all styles
  assets/wiki.css       styles for /wiki/ only, on top of style.css
  assets/logo.svg       dendrite mark, brand purple — the header, and the
                        favicon on a DARK browser theme
  assets/logo-ink.svg   the same mark in ink (#5b21b6) — the favicon on a
                        light browser theme, where the purple washes out
  assets/og.png         1200×630 social card
  assets/*.png          screenshots
posts/*.md              articles published to Hashnode (see below)
tools/build-wiki.py     renders the GitHub wiki into public/wiki/
```

## Deploying on Cloudflare

This deploys as a **Worker serving static assets**, not as a Pages project —
Cloudflare no longer offers Pages in the create flow on new accounts. There is no
Worker script: `wrangler.jsonc` points at `public/` and Cloudflare serves it.

In the dashboard, **Workers & Pages → Create → Workers → Import a repository**,
pick `velle999/synapseos-site`, and:

| Field | Value |
|---|---|
| Project name | `synapseos` |
| Build command | *(leave empty)* |
| Deploy command | `npx wrangler deploy` (the default) |
| Path | `/` |
| API token | leave on **Create new token** |

Every push to `main` redeploys. Non-production branches upload a preview version.

Deploying from this machine instead:

```sh
npx wrangler deploy --dry-run   # validate without shipping
npx wrangler deploy
```

`public/` is the whole story for what is reachable on the web: `README.md`,
`posts/` and `.github/` sit outside it and are never uploaded, which is why there
is no `.assetsignore`. **A new file only becomes public by being in `public/`.**

## The wiki

`https://soslinux.org/wiki/` is the project wiki, rendered as static pages. The
**wiki repo is the source** — it is edited on GitHub, exactly as before — and
`public/wiki/` is a generated mirror that is committed here.

```sh
tools/build-wiki.py                  # clone the published wiki, render it
tools/build-wiki.py --wiki ../SYNAPSE.wiki   # ...or use a local checkout
tools/build-wiki.py --check          # render to a temp dir and diff; 1 on drift
```

Needs `python-markdown` and `python-pygments`, both from the Arch repos.

**It runs here, not on Cloudflare.** The deploy has no build command and this
does not change that: what is served is what is in the repo, and it can be read,
diffed and reverted. The cost is that the site does not follow a wiki edit on
its own — after editing the wiki, run the script and push.

With no argument it **clones the published wiki** rather than reading a local
one, so the site mirrors what is public rather than whatever is unfinished in
somebody's working tree. Use `--wiki` when you want to preview an edit before it
is pushed.

### What it will refuse to do

Every `[label](Page)` in the wiki resolves against the page list, and every
`#anchor` against the headings of the page it points at, using **GitHub's**
slugify rather than python-markdown's — the anchors were written for GitHub, and
a fragment that matches nothing is not an error, it just leaves the reader at the
top of the right page. Anything unresolved is printed and the script exits 1
without writing.

### Things worth knowing before changing it

- **`script-src 'none'`.** No client-side search, no highlighter, no nav that
  toggles a class. The collapsible contents on a phone is a checkbox and a
  `:checked ~` rule, the same pattern as the homepage's theme switcher — not a
  `<details>`, whose UA-hidden content cannot be reliably re-shown by author CSS
  at a wider width.
- **`style-src 'self'`** refuses an inline `style=` attribute *silently*.
- The header nav is written **twice** — in `index.html` and in the generator's
  `HEADER_NAV`. There is no shared template, so changing one means changing the
  other.
- URLs are extensionless (`/wiki/Installation` serves `Installation.html`), which
  is Cloudflare's `auto-trailing-slash` handling. `_headers` therefore needs its
  own `/wiki/*` rule: `/*.html` matches the *request* path, and the request never
  carries the extension.
- `sitemap.xml` is regenerated by the script — one entry per page. Do not hand-
  edit it.

## The domain

The site is **https://soslinux.org**. The `synapseos.brncomputerhelp.workers.dev`
origin still answers — Cloudflare keeps it alongside a custom domain — but every
canonical, `og:url`, JSON-LD `@id` and sitemap entry names `soslinux.org`, so
that is the one search engines index.

The URL is written into five places. Changing it again means all of them:

1. `public/index.html` — `<link rel="canonical">`
2. `public/index.html` — the `og:url` and `og:image` / `twitter:image` meta tags
3. `public/index.html` — the `@id` and `url` fields in the JSON-LD block
4. `public/robots.txt` — the `Sitemap:` line
5. `public/sitemap.xml` — the `<loc>` element

Plus `ogImage` in any `posts/*.md` front matter.

```sh
git grep -ln 'soslinux\.org'   # finds all of them
```

**The DNS side is not in this repo.** The domain has to be added under the
project's **Custom domains** tab in Cloudflare *before* these URLs mean
anything — until it resolves, the canonical points at a host that does not
answer. Then re-verify the property and re-submit the sitemap in Google Search
Console; the old origin is a separate property there.

## Getting it indexed

1. Verify the domain in [Google Search Console](https://search.google.com/search-console)
   (Cloudflare DNS makes the TXT record a two-click job).
2. Submit `https://<domain>/sitemap.xml`.
3. Use **URL Inspection → Request indexing** on the homepage to skip the queue.
4. Check the structured data with the
   [Rich Results Test](https://search.google.com/test/rich-results) — the page
   declares `WebSite`, `SoftwareApplication` and `FAQPage`.

## Publishing to Hashnode

`posts/` holds the articles. The YAML front matter at the top of each file is
Hashnode's own format, but **it is documentation as much as automation** —
publishing from GitHub goes through Hashnode's API, and that requires a **Pro**
publication. On the free plan you paste the post into the editor and set the
same fields by hand.

### By hand (works on any plan)

Copy the body without the front matter — everything after the second `---`:

```sh
cd ~/synapseos-site   # the paths below are relative to the repo root
awk 'p{print} /^---$/{n++; if (n==2) p=1}' \
  posts/synapseos-llm-as-a-system-service.md | wl-copy
```

Paste that into a new Hashnode post, then set these in the editor. The mapping
is one-to-one, so nothing in the file goes unused:

| Front matter | Where it goes in the editor |
|---|---|
| `title` | the title line |
| `subtitle` | **Article settings** → Subtitle |
| `slug` | **Article settings** → Custom slug — set it, don't let it be derived |
| `tags` | the tag picker, up to 15 |
| `cover` | **Add cover image** → upload `assets/synui-desktop.png` |
| `seoTitle`, `seoDescription` | **Article settings** → SEO |
| `ogImage` | **Article settings** → OG image (needs the site deployed first) |
| `enableToc` | **Article settings** → Table of contents |

Editing later means editing in Hashnode, not in this file. Keep the file as the
source of the *text* and copy changes across, or accept the drift — but don't
assume a push updates the post, because on the free plan nothing here talks to
Hashnode at all.

### From GitHub (Pro)

`.github/workflows/publish-to-hashnode.yml` runs the
[Publish to Hashnode action](https://github.com/Hashnode/publish-github-action)
on any push touching `posts/`. It **skips with a notice** until both the
`HASHNODE_PAT` secret and a real `PUBLICATION_HOST` are set, so an unconfigured
repo stays green instead of sitting on a failed run.

1. Generate a Personal Access Token at <https://hashnode.com/settings/developer>.
2. Add it as the `HASHNODE_PAT` repository secret.
3. Replace `YOUR_BLOG.hashnode.dev` in the workflow's `env` block.

The `slug` is the update key: keep it stable and a re-push edits the existing
post rather than creating a second one.

### Notes that cost time if you don't know them

- **SVG covers are rejected.** Cover and inline images may be jpg/png/gif/webp/avif
  up to 8 MB. Under the action, relative paths upload to Hashnode's CDN and a
  leading `/` resolves from the repo root — which is why
  `cover: /assets/synui-desktop.png` works there. Uploading by hand, just pick
  the file.
- **No `canonical` on an original post.** The field is for articles first
  published elsewhere. These are written for Hashnode, so pointing their canonical
  at this site would ask Google to drop them from the index for no gain. Add
  `canonical:` only if the same text also goes up on a page of this site.
- **Deleting a markdown file does not delete the post.** Manage published posts
  from the Hashnode dashboard.
- `posts/` sits outside `public/`, so Cloudflare never serves the raw markdown
  into search results alongside the published article. It needs no `robots.txt`
  rule because it is not on the web at all.
- The `cover:` path is `/public/assets/...` — the Hashnode action resolves a
  leading `/` from the **repo root**, not from the site root.

## Keeping it accurate

The version number appears in `index.html` in the hero button, the download
section, the shell snippets and the JSON-LD `softwareVersion`. Bump all of them
when a new SynapseOS ISO ships:

```sh
git grep -n '0\.2\.6' index.html
```

## License

Same as the rest of the project: GPL-2.0-or-later. The SynapseOS name and the
dendrite mark are the project's.
