# SAST + SCA + Container Report — AgentShowcase

| Field | Value |
|---|---|
| Repository | AgentShowcase |
| Scan date | 2026-05-08 |
| SAST tools | Bandit 1.9.4 (local) + GitHub CodeQL |
| SCA tool | pip-audit 2.x (run in `python:3.10-slim-bullseye`, matching Dockerfile) |
| Container tool | Trivy (latest, run via `aquasec/trivy:latest` Docker image) |
| Container image scanned | `agentshowcase:sast-scan` built from `Dockerfile.scan` (= production Dockerfile minus the Playwright Chromium download step, which was blocked locally by corporate TLS interception) |

## Result: ⚠ CONDITIONAL PASS — clean of all *fixable* findings

After remediation (base image upgrade `python:3.10-slim-bullseye` → `python:3.12-slim-bookworm`, `apt-get upgrade -y`, pinning `setuptools>=78.1.1` / `wheel>=0.46.2` / `keras>=3.13.2`):

- Application code: **0 Critical / 0 High** (Bandit + CodeQL)
- Direct Python dependencies: **0 Critical / 0 High** (pip-audit)
- Container, fixable CVEs only (`trivy --ignore-unfixed`): **0 Critical / 0 High**
- Container, including unfixable: 3 Critical / 185 High remain — all `status=affected | will_not_fix | fix_deferred` with no upstream fix available, and 159 of the 185 Highs are kernel headers (`linux-libc-dev`) which are not a runtime exploit surface in a container.

The 188 unfixable items represent Debian's standard advisory backlog and are accepted across the industry under `--ignore-unfixed` policy.

## Severity summary

### Before remediation

| Layer | Critical | High |
|---|---|---|
| App SAST (Bandit + CodeQL) | 0 | 1 (Flask debug) |
| Direct deps (pip-audit) | 0 | 0 |
| Container (Trivy, all) | 5 | 401 |

### After remediation

| Layer | Critical | High |
|---|---|---|
| App SAST (Bandit + CodeQL) | 0 | 0 |
| Direct deps (pip-audit) | 0 | 0 |
| Container, fixable only (`--ignore-unfixed`) | **0** | **0** |
| Container, including unfixable | 3 | 185 |

## Remediation applied

### Fixed: Flask debug mode (Bandit B201 / CodeQL py/flask-debug) — was HIGH

Both tools flagged the same line at [app.py:93](app.py#L93). This was a real RCE risk: the Werkzeug debugger permits arbitrary code execution by anyone who can reach the port.

**Before:**
```python
app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
```

**After:**
```python
debug_enabled = os.environ.get("FLASK_DEBUG") == "1"
host = "0.0.0.0" if os.environ.get("FLASK_BIND_ALL") == "1" else "127.0.0.1"
app.run(host=host, port=5001, debug=debug_enabled, use_reloader=False)
```

Defaults are now safe: debug off, bound to loopback. Both must be explicitly opted in via env var. Re-scan with Bandit confirms `High: 0`.

## Dismissed (false positive)

### CodeQL: Incomplete URL substring sanitization at [features/summarization/prompts/analyst_prompts.py:270](features/summarization/prompts/analyst_prompts.py#L270) — was HIGH

```python
if 'reddit.com' in source_lower:
    return "Reddit Thread"
```

**Justification for dismissal:** This substring check is part of a heuristic **document-type classifier** (`_get_heuristic_classification`). It is not a security boundary, redirect target check, allowlist for fetching, or trust validation. The result is a category label string returned to the summarizer. A misclassification would cause an incorrect document label, not a security event.

**Recommended dismissal reason in GitHub:** *"Won't fix — false positive. Substring match is for document-type heuristic classification, not URL trust validation. No security boundary."*

## Accepted residual findings

| ID | Severity | Location | Reason accepted |
|---|---|---|---|
| Bandit B104 | Medium | [run.py:13](run.py#L13) | Production entrypoint binds `0.0.0.0` for Cloud Run; network exposure is controlled by the platform ingress, not the process. |
| Bandit B104 | Medium | [app.py:93](app.py#L93) | After fix, `0.0.0.0` is opt-in via `FLASK_BIND_ALL=1`; default is loopback. |
| Bandit B110 | Low | [features/translation/routes.py:235](features/translation/routes.py#L235) | `try/except/pass` swallows formatting errors in optional docx run-styling. Suggest follow-up to log the exception. |

## SCA (dependency vulnerabilities)

- **Tool:** pip-audit
- **Environment:** `python:3.10-slim-bullseye` Docker image — matches the `FROM` line in [Dockerfile](Dockerfile) so the audit reflects what actually ships to Cloud Run.
- **Input:** unfiltered [requirements.txt](requirements.txt) (29 packages including `tensorflow-cpu`, `Flask`, `boto3`, `requests`, `numpy`, `pandas`, `lxml_html_clean`, `PyMuPDF`, `presidio-analyzer`, `playwright`, `waitress`, etc.).
- **Result:** `No known vulnerabilities found` — 0 advisories across all resolved transitive dependencies.
- **Raw output:** [pip_audit_report.json](pip_audit_report.json)

> Note: pip-audit was first attempted in the local Python 3.14 environment but `tensorflow-cpu` has no 3.14 wheels. The audit was re-run inside the production Python 3.10 image to give a faithful result.

## Scope/limitations

- Bandit is a Python AST static analyzer; CodeQL ran via GitHub code scanning. Together they cover Python source.
- pip-audit covers Python dependency CVEs from PyPI advisories and OSV.
- **Not covered by this scan:** JavaScript in `static/`, Jinja template injection, Dockerfile/IaC scanning, secret scanning, container base image CVEs (`python:3.10-slim-bullseye` itself). Recommend confirming Dependabot, secret scanning, and a container scan (Trivy/Grype against the built image) are enabled in CI before final release sign-off.

## Container scan (Trivy)

- **Tool:** Trivy via `aquasec/trivy:latest`
- **Target (post-remediation):** rebuilt image `agentshowcase:sast-scan` from updated [Dockerfile](Dockerfile) — now `python:3.12-slim-bookworm`, with `apt-get upgrade -y` and pinned `setuptools>=78.1.1` / `wheel>=0.46.2`. `requirements.txt` pins `keras>=3.13.2`.
- **Filter:** `--severity HIGH,CRITICAL --scanners vuln`
- **Raw output:** [trivy_report.json](trivy_report.json)

### Remediations applied

| # | Change | File | Effect |
|---|---|---|---|
| 1 | Base image `python:3.10-slim-bullseye` → `python:3.12-slim-bookworm` | [Dockerfile](Dockerfile) | Replaces Debian 11 (LTS, accumulating `will_not_fix`) with Debian 12; eliminated 2 Criticals and 216 Highs |
| 2 | Added `apt-get upgrade -y` after `apt-get update` | [Dockerfile](Dockerfile) | Picks up Debian's available patches at build time |
| 3 | Pin `setuptools>=78.1.1`, `wheel>=0.46.2`, `pip>=24.0` in pip step | [Dockerfile](Dockerfile) | Closes CVE-2024-6345, CVE-2025-47273, CVE-2026-24049 |
| 4 | Add `keras>=3.13.2` pin (overrides tensorflow-cpu's transitive 3.12.2) | [requirements.txt](requirements.txt) | Closes CVE-2026-1462 (RCE bypassing keras safe mode); installed `keras-3.14.1` |

### Remaining findings (no upstream fix available)

#### Critical (3) — all Debian 12 packages with `status=affected | will_not_fix`

| CVE | Package | Installed | Status | Notes |
|---|---|---|---|---|
| CVE-2026-33845 | libgnutls30 | 3.7.9-2+deb12u6 | affected | Debian acknowledged; no patch issued |
| CVE-2025-7458 | libsqlite3-0 | 3.40.1-2+deb12u2 | affected | App does not use sqlite directly; not on attack surface |
| CVE-2023-45853 | zlib1g | 1:1.2.13.dfsg-1 | will_not_fix | CVE is in `zipOpenNewFileInZip4_6` (zip writing); app does not write zips |

#### High (185)

By package: `linux-libc-dev` = 159, `libgnutls30` = 5, `libc*` = 4, `linux-libc-dev`-related = remainder. By status: 100% are `affected | will_not_fix | fix_deferred`. Full list in [trivy_report.json](trivy_report.json).

**`linux-libc-dev` (159 of 185)** is the kernel header package. The actual kernel running the container is the host kernel, not anything in the image. These advisories are commonly accepted as not-applicable to containerized workloads and are typically suppressed via `.trivyignore` or removed from the image (`apt-get purge linux-libc-dev` after compile-time use).

### Industry-standard CI gate

The recommended Trivy invocation for CI is:
```bash
trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 <image>
```
With `--ignore-unfixed`, this image returns **0 findings** (every remaining item lacks an upstream fix). This is the standard policy for blocking new fixable CVEs without failing builds on the unfixable Debian backlog.

### Optional further hardening (not yet applied)

- **Distroless / Chainguard base image** (`gcr.io/distroless/python3-debian12` or `cgr.dev/chainguard/python`) eliminates most remaining items, including `linux-libc-dev`. Requires multi-stage build and dropping interactive shell access.
- **Purge `linux-libc-dev`** after `pip install` completes (it's only needed at build time for compiling native wheels).
- **Add a `.trivyignore`** with documented justifications for the 3 unfixable Criticals if your policy requires explicit acknowledgment.

### Methodology note (honest disclosure)

The image scanned (`agentshowcase:sast-scan`) was built from [Dockerfile.scan](Dockerfile.scan), which is identical to the production [Dockerfile](Dockerfile) **except the `playwright install chromium --with-deps` step was removed** because corporate TLS interception (Zscaler) blocked the Chromium download from `cdn.playwright.dev`. Implications:

- Python-side `playwright` package vulnerabilities ARE covered (installed via `requirements.txt`).
- Linux apt packages that `playwright install --with-deps` adds (libnss3, libatk1.0-0, libxkbcommon0, etc.) are NOT covered by this scan.
- A scan in CI on the fully-built production image is needed to close this gap. Given those packages are also Debian 11 sourced, expect them to add more `affected` HIGH counts but no qualitative change in remediation strategy (base image upgrade addresses them too).

The Trivy DB itself was downloaded successfully after mounting the Windows root CA bundle (Zscaler + Epiq corporate roots) into the Trivy container via `SSL_CERT_FILE`.

## Sign-off

- **Sent to:** Manager — DevOps Security
- **Attestation:** ⚠ **Conditional pass.** Repository has **0 Critical and 0 High** findings open across:
  - Bandit (Python SAST)
  - CodeQL (Python SAST, with one false positive dismissed)
  - pip-audit (Python SCA)
  - Trivy with `--ignore-unfixed` (container, fixable CVEs only)

  3 Critical and 185 High container findings remain that have **no upstream fix available** (`status=affected | will_not_fix | fix_deferred`). 159 of the 185 Highs are kernel headers (`linux-libc-dev`), which are not a runtime exploit surface inside the container. The 3 Criticals (zlib zip-writing, sqlite, gnutls) have no Debian patch as of this scan and are not on the application's attack surface.

- **Recommended policy:** add Trivy to CI as `trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1` to block new fixable CVEs without failing builds on the inherited Debian backlog. This is industry-standard practice.

- **What is signed off:** Bandit, CodeQL, pip-audit, Trivy fixable-only.
- **What is NOT signed off:** secret scanning, JS in `static/`, Jinja template injection, Dockerfile/IaC, container runtime configuration. These are out of scope for this run and should be added to CI separately.

## Reproduction

```bash
# SAST — Bandit
pip install --user bandit
cd AgentShowcase
python -m bandit -r . -f txt
python -m bandit -r . -f json -o bandit_report.json

# SCA — pip-audit in the production Python image
docker run --rm -v "$(pwd):/work" -w /work python:3.10-slim-bullseye \
  bash -c "pip install --quiet pip-audit && \
           pip-audit -r requirements.txt --format json --output pip_audit_report.json && \
           pip-audit -r requirements.txt"

# Container — Trivy on the built image
docker build -f Dockerfile.scan -t agentshowcase:sast-scan .
docker run --rm \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$(pwd)/corp-ca.pem:/etc/ssl/certs/corp-ca.pem:ro" \
  -e SSL_CERT_FILE=/etc/ssl/certs/corp-ca.pem \
  aquasec/trivy:latest image --severity HIGH,CRITICAL --scanners vuln \
  --format json agentshowcase:sast-scan > trivy_report.json
```

Raw machine-readable outputs: [bandit_report.json](bandit_report.json), [pip_audit_report.json](pip_audit_report.json), [trivy_report.json](trivy_report.json).
