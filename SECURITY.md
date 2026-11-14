# Security Policy

## Security model

LinkGraph is a single-user tool. It runs on your own machine, reads a LinkedIn data export from
your Downloads folder, and serves a web UI to your browser. That export holds personal data about
other people (names, job titles, private messages), so the design keeps it on the machine.

**Where it runs.** Uvicorn binds `127.0.0.1` only. Nothing listens on your LAN.

**No login, by design.** Reaching `127.0.0.1` is the gate. To keep a web page in your browser
from using that gate, the server checks the `Host` header against an allowlist (`127.0.0.1`,
`localhost`), which blocks DNS rebinding. Write endpoints accept JSON bodies only, so a cross-site
form cannot change your notes. No CORS headers are sent, so other origins cannot read responses.

**No external requests, with one opt-in exception.** The page loads only same-origin files: the
graph library is vendored in `static/vendor/`, and a Content-Security-Policy blocks every other
origin. There is no telemetry.

The exception is **Fetch logos**, which runs only after a confirmation dialog, or when you save
a domain for a company. Then the server sends company names to `data.brreg.no` and
`www.wikidata.org`, and company domains to `icons.duckduckgo.com`. People are never sent. When
the icon service has no icon, the server asks the company's own website for one.

That last step takes a domain from outside data, so it is guarded against SSRF
(`linkgraph/siteicons.py`): https on port 443 only, no credentials in URLs, the host must resolve
to public addresses only (every private, loopback, link-local, CGNAT, reserved and multicast range
is refused, and so is a mixed answer), the connection goes to the exact IP that passed the check
(no DNS-rebinding window) while TLS still verifies the hostname, and each of at most three
redirects is checked the same way. Responses are size-capped, and only raster images that pass a magic-byte check
(PNG, ICO, GIF, JPEG, WebP; never SVG) are cached. The cache lives in `logo-cache/` and the page
loads logos from `127.0.0.1`.

**Data handling.** Zips are read in memory and never extracted. Export content is HTML-escaped
before it reaches the page. Your lead statuses and notes are stored in `linkgraph-notes.json` in
the project folder, which git ignores.

**Out of scope.** Running it on a shared or internet-facing host, multiple users, and defending
against someone who already has access to your user account.

## Supported Versions

Only the latest version on `main` is supported with security updates.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.
Use the "Report a vulnerability" button under this repository's **Security** tab
(private vulnerability reporting is enabled). You will receive an acknowledgement
within 48 hours.
