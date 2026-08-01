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
