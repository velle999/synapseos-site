# synapseos-site

The public website for **[SynapseOS](https://github.com/velle999/SYNAPSE)** — an
Arch-based Linux distribution with a local LLM wired into the system layer.

Live at **https://synapseos.pages.dev/**

It is a static site with no build step, no framework and no external requests —
every asset is served from this repo, which is also what the `Content-Security-Policy`
in `_headers` enforces.

```
index.html          the page (content, metadata, JSON-LD)
404.html            not-found page
robots.txt          crawl policy + sitemap pointer
sitemap.xml         one URL; bump <lastmod> on a content change
_headers            Cloudflare Pages: caching + security headers
assets/style.css    all styles
assets/logo.svg     dendrite mark (transparent, used as favicon)
assets/og.png       1200×630 social card
assets/*.png        screenshots
posts/*.md          articles published to Hashnode (see below)
```

## Deploying on Cloudflare Pages

Connect this repo in the Cloudflare dashboard (Workers & Pages → Create → Pages →
Connect to Git) with:

| Setting | Value |
|---|---|
| Framework preset | None |
| Build command | *(leave empty)* |
| Build output directory | `/` |
| Production branch | `main` |

Every push to `main` redeploys. Pull requests get preview URLs automatically.

## Changing the domain

The site URL is written into five places. When a real domain replaces
`synapseos.pages.dev`, update all of them:

1. `index.html` — `<link rel="canonical">`
2. `index.html` — the `og:url` and `og:image` / `twitter:image` meta tags
3. `index.html` — the `@id` and `url` fields in the JSON-LD block
4. `robots.txt` — the `Sitemap:` line
5. `sitemap.xml` — the `<loc>` element

```sh
git grep -l 'synapseos.pages.dev'   # finds all of them
```

Then add the custom domain under the project's **Custom domains** tab in
Cloudflare, and re-submit the sitemap in Google Search Console.

## Getting it indexed

1. Verify the domain in [Google Search Console](https://search.google.com/search-console)
   (Cloudflare DNS makes the TXT record a two-click job).
2. Submit `https://<domain>/sitemap.xml`.
3. Use **URL Inspection → Request indexing** on the homepage to skip the queue.
4. Check the structured data with the
   [Rich Results Test](https://search.google.com/test/rich-results) — the page
   declares `WebSite`, `SoftwareApplication` and `FAQPage`.

## Publishing to Hashnode

`posts/` holds articles in Hashnode's markdown format, published by
`.github/workflows/publish-to-hashnode.yml` through the
[Publish to Hashnode action](https://github.com/Hashnode/publish-github-action).
The `slug` in each file's front matter is the update key — keep it stable and a
re-push edits the existing post instead of creating a second one.

Setup (one time):

1. Publishing through the API **requires Hashnode Pro**. Without it, open the
   post file and paste its body into the Hashnode editor by hand — the front
   matter maps onto fields in the editor's settings panel.
2. Generate a Personal Access Token at <https://hashnode.com/settings/developer>.
3. Add it as the `HASHNODE_PAT` repository secret.
4. Replace `YOUR_BLOG.hashnode.dev` in the workflow with your publication host.

Notes that cost time if you don't know them:

- **SVG covers are rejected.** Cover and inline images may be jpg/png/gif/webp/avif
  up to 8 MB. Relative paths upload to Hashnode's CDN automatically; a leading `/`
  resolves from the repo root, which is why `cover: /assets/synui-desktop.png`
  works.
- **No `canonical` on an original post.** The field is for articles first
  published elsewhere. These are written for Hashnode, so pointing their canonical
  at this site would ask Google to drop them from the index for no gain. Add
  `canonical:` only if the same text also goes up on a page of this site.
- **Deleting a markdown file does not delete the post.** Manage published posts
  from the Hashnode dashboard.
- `robots.txt` disallows `/posts/` so Cloudflare never serves the raw markdown
  into search results alongside the published article.

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
