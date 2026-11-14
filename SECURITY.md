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

**No external requests.** The server makes no outbound calls. The page loads only same-origin
files: the graph library is vendored in `static/vendor/`, and a Content-Security-Policy blocks
every other origin. There is no telemetry.

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
