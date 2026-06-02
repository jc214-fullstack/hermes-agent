# Streamed PK → Stremio Sports Addon Blueprint

## Goal

Build a Stremio addon that turns Streamed PK-style data into a sports-first browsing experience inside Stremio.

The addon should:

- expose a searchable sports catalog
- let users drill into matches by sport, then by matchup
- present match-level metadata cleanly in Stremio
- return multiple stream choices per match when available
- keep the UI aligned with what Stremio actually supports natively

Assumption: the upstream Streamed PK source is authorized for your use case. This blueprint does not include any bypasses or scraping tricks.

## Core design choice

Use the Stremio addon protocol in Node.js.

Reason: Stremio addons are HTTP-based and language-agnostic, but Node.js is the fastest path because the addon SDK, JSON routing, and common examples all map cleanly to this style of implementation.

## Product constraints

What Stremio can do well:

- catalog browsing
- match detail pages
- multiple stream choices per event
- concise metadata
- external links

What Stremio does not do natively:

- a dedicated odds table UI
- rich sportsbook-style live betting panels
- arbitrary custom widgets on the default addon surfaces

So the design should surface odds as metadata text, optional external links, or source notes — not as a native table component.

---

## Data mapping model

### Streamed PK → Stremio

| Streamed PK object | Stremio surface | Notes |
| --- | --- | --- |
| Sport category | catalog entry | one catalog per sport plus All Sports / Live Now |
| Match | meta object of type `tv` | title should be the matchup, with sport name in the description |
| Stream source | stream item | one or more streams per match |
| Odds | description / external URL text | no native odds UI |
| Match image / poster | `poster` / `background` fields in meta | use if available |

### Recommended ID scheme

Keep IDs stable and parseable.

- Sport catalog ID: `sport:<slug>`
- Match meta ID: `spk:match:<matchId>`
- Stream source ID (internal only): `spk:stream:<matchId>:<sourceKey>`

This makes routing predictable and lets the addon rebuild the same Stremio IDs from Streamed PK data.

---

## Exact manifest shape

The manifest should be generated dynamically from the current sports list so the addon stays searchable and current.

```json
{
  "id": "com.yourname.streamedpk.sports",
  "version": "1.0.0",
  "name": "Streamed PK Sports",
  "description": "Browse live sports, matches, and available streams from Streamed PK-style data.",
  "resources": ["catalog", "meta", "stream"],
  "types": ["tv"],
  "catalogs": [
    {
      "type": "tv",
      "id": "sports-all",
      "name": "All Sports"
    },
    {
      "type": "tv",
      "id": "sports-live",
      "name": "Live Now"
    },
    {
      "type": "tv",
      "id": "sport-football",
      "name": "Football"
    },
    {
      "type": "tv",
      "id": "sport-basketball",
      "name": "Basketball"
    }
  ]
}
```

### Manifest rules

- `types` should stay on `tv` for live sports events.
- `catalogs` should be derived from the upstream sports list.
- Keep the manifest simple; the heavy lifting belongs in the catalog/meta/stream handlers.
- If a sport disappears upstream, the manifest should stop advertising that catalog on the next refresh.

---

## Endpoint map

Use the standard Stremio addon endpoints plus one lightweight health route.

### Public addon routes

- `GET /manifest.json`
  - returns the addon manifest
  - builds catalog entries from the current sports list

- `GET /catalog/tv/sports-all.json`
  - returns all active/upcoming matches across all sports

- `GET /catalog/tv/sports-live.json`
  - returns only live matches

- `GET /catalog/tv/sport-<slug>.json`
  - returns matches for one sport category

- `GET /meta/tv/spk:match:<matchId>.json`
  - returns one match detail object

- `GET /stream/tv/spk:match:<matchId>.json`
  - returns all available streams for that match

### Support route

- `GET /healthz`
  - returns `{ ok: true }`
  - used for deployment checks and local smoke tests

### Notes on route behavior

- `catalog` routes should accept the standard Stremio `extra` parameters if needed later, but the MVP can work without extras.
- `meta` should reconstruct the match from the source API and render a clean Stremio detail object.
- `stream` should prefer directly playable URLs.
- If the upstream source only provides an embed page, do not assume that `embedUrl` is directly playable in Stremio.

---

## Suggested file-by-file starter code design

### `package.json`

Responsibilities:

- Node.js package metadata
- dependencies for HTTP server and fetch
- scripts for dev, build, and test

Suggested scripts:

- `dev` → run local server
- `start` → run production server
- `test` → run unit tests
- `lint` → optional static checks

---

### `src/config.ts`

Responsibilities:

- environment parsing
- base URL for Streamed PK API
- server port
- cache TTLs
- optional feature flags

Example values:

- `STREAMEDPK_BASE_URL`
- `PORT`
- `CACHE_TTL_SECONDS`

---

### `src/client/streamedpk.ts`

Responsibilities:

- fetch sports
- fetch matches by sport
- fetch live matches
- fetch one match’s stream list
- normalize raw upstream responses

This should be the only file that knows the upstream REST shape.

---

### `src/lib/id.ts`

Responsibilities:

- build stable Stremio IDs
- parse IDs back into source identifiers
- escape unsafe characters

Example helpers:

- `makeMatchId(matchId: string): string`
- `parseMatchId(id: string): string | null`
- `makeSportCatalogId(slug: string): string`

---

### `src/lib/mappers.ts`

Responsibilities:

- convert Streamed PK sports into manifest catalogs
- convert Streamed PK matches into Stremio meta objects
- convert Streamed PK streams into Stremio stream objects

This file should contain the core data-shaping logic.

Key mapping rules:

- title = matchup text
- description = sport + kickoff time + optional odds summary
- poster/background = upstream image if available
- stream list = all playable sources for the event

---

### `src/lib/cache.ts`

Responsibilities:

- in-memory response caching
- simple TTL for sports and match lists
- deduping upstream fetches during hot refreshes

Why it matters:

- `/manifest.json` may need sports data on every refresh
- catalog pages may be hit repeatedly by the client
- caching reduces upstream pressure and stabilizes browsing

---

### `src/routes/manifest.ts`

Responsibilities:

- return addon manifest JSON
- compose catalogs dynamically from `/api/sports`
- keep the list aligned with current upstream sport categories

---

### `src/routes/catalog.ts`

Responsibilities:

- handle `sports-all`
- handle `sports-live`
- handle `sport-<slug>`
- fetch the right upstream match list
- map matches into Stremio catalog meta objects

Behavior:

- show only active/upcoming entries in All Sports
- show only live events in Live Now
- keep per-sport pages narrow and browsable

---

### `src/routes/meta.ts`

Responsibilities:

- resolve a single match by Stremio ID
- build the Stremio meta object
- include match description, images, and any source notes

The meta object should be concise and readable in the Stremio detail page.

---

### `src/routes/stream.ts`

Responsibilities:

- resolve a match into stream options
- return one stream object per playable source
- include labels like source name, HD flag, language, or quality if known

Important:

- `url` should be a playable URL if possible
- `externalUrl` is a fallback when the source cannot be played directly
- do not rely on `embedUrl` alone as the final stream payload

---

### `src/server.ts`

Responsibilities:

- create the HTTP server
- mount route handlers
- expose the addon under standard Stremio paths
- expose `/healthz`
- log startup and errors

---

### `src/index.ts`

Responsibilities:

- application entry point
- load config
- start server
- handle shutdown signals cleanly

---

### `test/*.test.ts`

Responsibilities:

- verify manifest shape
- verify catalog ID generation
- verify match-to-meta mapping
- verify stream mapping
- verify edge cases like missing images or empty stream lists

---

## Starter folder layout

```text
streamedpk-stremio-addon/
├── package.json
├── tsconfig.json
├── README.md
├── .env.example
├── src/
│   ├── index.ts
│   ├── server.ts
│   ├── config.ts
│   ├── client/
│   │   └── streamedpk.ts
│   ├── lib/
│   │   ├── id.ts
│   │   ├── mappers.ts
│   │   └── cache.ts
│   └── routes/
│       ├── manifest.ts
│       ├── catalog.ts
│       ├── meta.ts
│       └── stream.ts
└── test/
    ├── manifest.test.ts
    ├── catalog.test.ts
    └── stream.test.ts
```

---

## MVP implementation phases

### Phase 1: protocol skeleton

- create the Node.js app
- serve `/manifest.json`
- serve empty-but-valid catalog and stream responses
- confirm Stremio can install and hit the addon

### Phase 2: sports catalog

- fetch sports from upstream
- generate sport catalogs
- render All Sports and Live Now
- verify category browsing works

### Phase 3: match details

- map each match to a Stremio meta object
- add team names, kickoff times, and images
- verify the detail page is readable

### Phase 4: streams

- map each match to one or more streams
- prefer direct playable URLs
- fall back to external handling where necessary

### Phase 5: polish

- cache upstream requests
- improve sorting and filtering
- improve match descriptions and labels
- add tests and smoke validation

---

## Validation checklist

Before calling the addon done, verify:

- manifest installs in Stremio
- sports catalogs show up correctly
- sports pages are searchable and browsable
- match pages open with the right matchup title
- stream list shows multiple sources when available
- no unsupported Stremio fields are required for the core UX
- the addon still works when a sport or match disappears upstream
- the server returns healthy responses under `/healthz`

---

## Practical UX recommendation

If you want the front end to feel like the Streamed PK site:

- make the catalog pages mirror the upstream sport categories
- use the match title as the primary browsing unit
- keep odds in the description, not in a special widget
- make the stream list source-labeled and compact
- keep the addon fast and shallow rather than overcomplicated

That gives you the closest Stremio-native equivalent to the Streamed PK browsing flow.
