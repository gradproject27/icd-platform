# Authentication approach and MVP threat model

| | |
|---|---|
| **Project** | ICD (Intelligent Cyber Defense) |
| **Workstream** | C5 Incident Response & Security Assurance |
| **Task** | T1-14 (Week 1) |
| **Status** | Draft for team review |
| **Related** | `docs/response-workflow-spec.md` (T1-13) |

## 1. Purpose and scope

This document has three parts:

- **Part A** describes the authentication and session approach that C5 implements from Week 2: seeded users and login in T2-15, then full authentication and role-based access control (RBAC) in Phase 2.
- **Part B** updates the MVP threat model (TM-01 to TM-12) and proposes one new threat (TM-13).
- **Part C** lists the open questions.

This is documentation only. It adds no code, dependencies, migrations or contract changes. All response actions in ICD remain simulated, labelled `SIMULATED` and audited (NFR-SF-01, NFR-SF-07).

Every item marked **(proposed, needs team agreement)** is a C5 design choice that the team has not yet agreed. Each one also appears in Part C. Source IDs are given next to each rule.

No real password, key or token appears in this document. Values that would be secret are written as placeholders such as `<set-in-.env>`.

---

# Part A: Authentication approach

## A1. Requirements it must meet (approved)

| ID | Requirement | Where Part A meets it |
|---|---|---|
| NFR-S-01 (Must) | All dashboard and API access requires authentication, except the health check. Passwords are hashed (team choice: Argon2). Sessions or tokens expire. | A2.1, A2.3, A2.9 |
| C-01 | Every dashboard page and API route requires a valid session. Only `/health` is open. | A2.1, A2.3 |
| C-02 | Passwords are stored only as salted Argon2 hashes. Login errors do not reveal which field was wrong. Failed logins are logged. | A2.4, A2.9 |
| C-03 | Sessions expire after a fixed lifetime and after inactivity. Logout invalidates them. | A2.3, A2.5, A2.6 |
| C-04, FR-39, NFR-S-02 | The permissions of the four roles are checked on the server for every action, with deny by default. Hiding a button is never the only protection. Refusals are recorded. | A2.13, A3 |
| C-05, NFR-S-03 | TLS on browser-to-API traffic. Scope per TD-12: browser–API, database and HPC links. | A2.2 (`Secure` cookie) |
| C-06, NFR-S-03 | Secrets come from environment variables, never from source code or images. The secret scan (gitleaks, already in CI) runs on every pull request. | A2.12 |
| C-14, NFR-S-04 | Logins, logouts, failed logins and refusals are audited, append-only. | A2.4, A2.5, A2.7, A2.11 |
| C-19 (proposed control, decided by TD-8 at W6) | Login rate limiting and account lockout. MFA only if the supervisor asks. | A2.11 |

## A2. Design

All items in this section are **(proposed, needs team agreement)**.

### A2.1 Server-side sessions, not JWT

On a successful login the server:

1. creates a random opaque token with `secrets.token_urlsafe(32)` (256 bits);
2. stores only the token's SHA-256 hash in a PostgreSQL `session` table;
3. sends the token to the browser in a cookie (A2.2).

| `session` column | Meaning |
|---|---|
| token hash | SHA-256 of the token (the token itself is never stored) |
| user ID | the session's user |
| role | the user's role at login (one role per user, A2.13) |
| `created_at` | login time |
| `last_seen_at` | time of the last authenticated request |
| `expires_at` | `created_at` + absolute lifetime (A2.3) |
| `revoked_at` | set on logout or invalidation (A2.5, A2.6); empty while valid |

On every request the server hashes the token from the cookie and looks it up. If no row matches, the request is refused.

**Reason.** Logout and role changes must take effect immediately (C-03). A self-contained JWT stays valid until it expires unless the server keeps a revocation list, which removes JWT's advantage. A server-side session is revoked by updating one row.

### A2.2 Session cookie

| Attribute | Value | Reason |
|---|---|---|
| Name | `icd_session` | |
| `HttpOnly` | set | Page scripts cannot read the token, so cross-site scripting (XSS) cannot steal it directly (TM-10). |
| `Secure` | set | The cookie is sent only over TLS (C-05, NFR-S-03). |
| `SameSite=Strict` | set | The browser does not send the cookie on requests started by another site (CSRF defence, A2.7). |
| `Path` | `/` | |
| `Domain` | not set | The cookie stays on the exact host that set it. |

The token is never put in `localStorage`, in a URL or in a log line.

Note for local development: most current browsers treat `http://localhost` as a secure context and accept `Secure` cookies there. On any other host, TLS is required (C-05).

### A2.3 Expiry

| Limit | Value | Checked against |
|---|---|---|
| Idle timeout | **30 minutes** | `last_seen_at` |
| Absolute lifetime | **8 hours** | `expires_at` |

On each request the server checks both limits and `revoked_at`. If the session is valid, it updates `last_seen_at`. An expired or revoked session is refused with HTTP 401. A periodic clean-up job deletes expired sessions (C-03, NFR-S-01).

### A2.4 Login

`POST /auth/login` takes a username and a password.

- **New token on every login.** Every successful login issues a new session token. A token that existed before login is never reused, which prevents session fixation (TM-10).
- **One message for every failure.** Every failure returns the same message ("Invalid username or password") and the same HTTP status (C-02).
- **Constant work for unknown users.** If the username is unknown, the server still runs one Argon2 verify against a dummy hash. A wrong username and a wrong password then take about the same time, so timing does not reveal which was wrong (C-02).
- **Audit.** Every successful and failed login writes an audit record (C-02, C-14, NFR-S-04).

### A2.5 Logout

`POST /auth/logout` sets `revoked_at` on the server and clears the cookie. Logging out with an already-expired session still clears the cookie. Every logout is audited (C-03, C-14).

### A2.6 Invalidation

All sessions of a user are revoked (`revoked_at` set) when:

- the user's password changes;
- the user's role changes;
- the account is disabled.

The change takes effect on the user's next request (C-03, TM-03, TM-10).

### A2.7 CSRF

- The `SameSite=Strict` cookie (A2.2) is the first defence.
- On every state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`), the server also checks that the `Origin` header matches the dashboard's origin. The dashboard and the API share one origin, so the allow-list has a single entry (A2.14).
- A request from another origin is refused, and the refusal is audited (C-04, C-14, FR-39).

### A2.8 WebSocket (countdown channel)

At the WebSocket handshake, the server checks the same `icd_session` cookie and the `Origin` header.

While the socket is open, the server closes it as soon as the session expires or is revoked. A socket never outlives its session (C-01, C-03).

The countdown events themselves are defined in `docs/response-workflow-spec.md` section 7.

### A2.9 Argon2

- **Algorithm:** Argon2id, through the `argon2-cffi` library. The library is added and pinned in Week 2, not in this task (CONTRIBUTING.md: pin dependency versions).
- **Parameters:** the library defaults (time cost 3, memory 64 MiB, parallelism 4), which follow RFC 9106's second recommended option.
- **Salt:** a random salt per hash, stored inside the encoded hash (C-02).
- **Rehash:** on a successful login, the server calls `check_needs_rehash`. If the parameters have changed since the hash was made, it rehashes the password and stores the new hash.

### A2.10 Password policy

- Length: minimum 12 characters, maximum 128.
- No composition rules (no forced digits, symbols or mixed case).
- Checked against a small list of common passwords.

This follows the style of NIST SP 800-63B.

### A2.11 Rate limiting and lockout (C-19, pending TD-8 at W6)

- At most **5 failed logins per username in 15 minutes**. After that, the account is locked for **15 minutes**.
- During a lockout, login attempts are refused with the same message as any other failure (A2.4), so the response does not reveal that the account exists.
- Every failure and every lockout is audited (C-14).
- The System Administrator can unlock a locked account before the 15 minutes end (B4).
- MFA is out of scope unless the supervisor asks for it (C-19).

### A2.12 No hardcoded credentials

The prototype's seeded users (T2-15) are created by a seed command. For each user, the command either:

- reads the initial password from an environment variable, for example `ICD_SEED_ANALYST_PASSWORD=<set-in-.env>` in `.env.example`; or
- generates a random password and prints it once to the operator's terminal, never to a log.

No password, hash or token is ever committed. The gitleaks job in CI checks every pull request (C-06, NFR-S-03).

The `.env.example` entries are added in T2-15, not in this task.

### A2.13 One role per user

Each user has exactly one of the four roles in the MVP. The session stores that role (A2.1). A role change revokes all of the user's sessions (A2.6), so a session never carries an old role (C-04, TM-03).

### A2.14 Same origin for dashboard and API

Decided by C1 **(proposed, needs C4 agreement)**.

In the current Compose setup, the dashboard (`web`, port 8080) and the API (`api`, port 8000) would be different origins. Instead, the `web` service reverse-proxies `/api` and `/ws` to the `api` service, so the browser sees one origin. As a result:

- the cookie stays `SameSite=Strict` (A2.2);
- the `Origin` check allow-lists a single origin (A2.7, A2.8);
- no CORS configuration is needed.

C1 implements the proxy before T2-15.

## A3. Roles and initial permissions

The four roles are exactly **SOC Analyst**, **SOC Manager**, **Security Engineer** and **System Administrator** (D7.1). OD-24 decides the final permissions at W5.

Each cell is one of:

- **Allowed (decided):** approved.
- **Allowed (OD-24 proposal):** proposed in the v1 role-permission matrix, awaiting OD-24.
- **Denied:** not allowed.

Every action that this table does not list as allowed is denied by default. Every permission is checked on the server; hiding a button in the dashboard is never the only protection, and every refusal is audited (C-04, FR-39, NFR-S-02).

| Action | SOC Analyst | SOC Manager | Security Engineer | System Administrator |
|---|---|---|---|---|
| Log in and hold a session | Allowed (decided) | Allowed (decided) | Allowed (decided) | Allowed (decided) |
| View incidents, evidence and AI reports | Allowed (decided) | Allowed (decided, D7.2) | Allowed (OD-24 proposal) | Denied (until OD-24) |
| Approve, reject or select a response, and act in the 60-second window | Allowed (decided, D1.2) | Denied (OD-24 proposal: reviews but makes no response decisions in the MVP) | Denied | Denied |
| Receive escalations and access reports | Denied | Allowed (decided, D7.2) | Denied | Denied |
| Upload logs and datasets | Denied | Denied | Allowed (OD-24 proposal: evaluation datasets) | Allowed (OD-24 proposal, v1 cell) |
| Manage users and roles | Denied | Denied | Denied | Allowed (OD-24 proposal, v1 cell) |
| Configure system-level settings and approved response scenarios | Denied | Denied | Allowed (decided, D7.5) | Denied |
| Configure thresholds, timing and policies | Denied | Denied | Denied | Allowed (OD-24 proposal, v1 cell) |
| Manage correlation rules; evaluate correlation | Denied | Denied | Allowed (OD-24 proposal, v1 cells) | Denied |
| Review audit records | Allowed (OD-24 proposal: own incidents only, v1 cell) | Denied | Denied | Allowed (OD-24 proposal, v1 cell) |
| Edit or delete audit records | Denied (C-14, FR-35) | Denied (C-14, FR-35) | Denied (C-14, FR-35) | Denied (C-14, FR-35) |

Notes:

1. **The 60-second window is fixed.** No role can configure it in the MVP (OD-17). "Configure thresholds, timing and policies" does not include it.
2. **Confirming `Resolved` → `Closed` is undecided.** The response workflow spec (transition T13) leaves the confirming role to OD-24, so this table does not list it. Until OD-24 decides, deny by default applies.
3. **A notification is not the "receive escalations" permission.** When a freeze starts, a dashboard notification goes to both the SOC Analyst and the SOC Manager (FR-26, FR-43; response spec transition T03). The "receive escalations" row is a separate permission: only the SOC Manager gets the escalation view (D7.2). The two do not conflict. OD-24 confirms both at W5 (Part C, question 10).

---

# Part B: Updated MVP threat model

## B1. Rating scale (unchanged)

- Likelihood (L) and Impact (I) are each rated from 1 to 3.
- **Risk = L × I.** 1–2 is Low, 3–4 is Medium, 6–9 is High.

The approved IDs TM-01 to TM-12 and their original ratings are kept.

The Part A design adds controls to TM-03 and TM-10. Their ratings are still **not lowered**, because the controls are proposed and not yet tested (AS-12, AS-13). A rating may be lowered only after the planned test passes.

TM-13 is a **(proposed new ID, needs team agreement)**. Its ratings are proposed on the same basis as the similar rows TM-02, TM-03 and TM-11.

## B2. Threat table

Planned test weeks follow the roadmap gates:

| Gate | Date | Tests due |
|---|---|---|
| W2 | Week 2 (before M4) | AS-10 fake-clock tests |
| M4 | W4, Sun 15 Nov 2026 | AS-09, AS-10 |
| M5 | W9, Sun 20 Dec 2026 | AS-02, AS-04, AS-05, AS-06, AS-12, AS-13 (first version), AS-14, AS-15, AS-18, AS-19 |
| M6 | W14, Sun 24 Jan 2027 | AS-08, AS-13 (final) |
| M9 | W20 | AS-17 |

| ID | Threat | Scenario in ICD | Likely impact | L | I | Risk | Controls | Planned test and week | Owner |
|---|---|---|---|---|---|---|---|---|---|
| TM-01 | Malicious or malformed uploaded file | A crafted or corrupt log file is uploaded and breaks the parser or exploits it. | Ingestion crash, corrupted events, or code execution in the parser | 2 | 3 | 6 High | C-07, C-08, C-18 (proposed) | AS-02 by M5 (W9) | C2 |
| TM-02 | Unauthorized access to incident records and log data | A user without a session, or with a role that is not allowed, reads incidents, evidence or logs through the dashboard or the API. | Disclosure of sensitive security data | 2 | 3 | 6 High | C-01, C-04, C-05; Part A2.1–A2.3, A3 | AS-12, AS-15 by M5 (W9) | C5 |
| TM-03 | Privilege escalation: unauthorized role or configuration change | A user changes their own or another user's role, or changes system configuration, without the right role. | Loss of separation of duties; unsafe configuration | 2 | 3 | 6 High | C-04, C-14; one role per user (A2.13, proposed); sessions revoked on role change (A2.6, proposed) | AS-12 and AS-13 (first version) by M5 (W9); AS-13 (final) by M6 (W14) | C5 |
| TM-04 | Tampering with uploaded evidence or incident records | Evidence or incident data is changed after ingestion, so analysis or audit no longer matches the source. | Wrong decisions; loss of evidential value | 2 | 3 | 6 High | C-14, C-16 (proposed) | AS-15 by M5 (W9) | C2, C1 |
| TM-05 | AI produces unsupported or misleading analysis | The LLM report contains claims that the evidence does not support, or cites events that do not exist. | Analyst misled into a wrong decision | 3 | 3 | 9 High | C-11; confidence gate (OD-16) | AS-05 by M5 (W9) | AI1 |
| TM-06 | Prompt injection through untrusted log content | Attacker-controlled text in a log field instructs the LLM to change its analysis or recommendation. | Manipulated analysis; a wrong recommendation shown to the analyst | 2 | 3 | 6 High | C-09, C-10, C-12 | AS-08 by M6 (W14) | AI1, C5 |
| TM-07 | Incorrect correlation, risk or confidence wrongly starts or prevents a freeze | A correlation, risk-score or confidence error starts a freeze on a harmless incident, or misses a High incident. | Unneeded simulated response, or a missed one | 2 | 3 | 6 High | C-17 (proposed), NFR-SF-06 | AS-09 by M4 (W4); AS-04, AS-06 by M5 (W9) | C3 |
| TM-08 | Audit records modified or omitted | Application code or a user updates or deletes audit rows, or a transition commits without its audit row. | Loss of accountability; untraceable decisions | 2 | 2 | 4 Medium | C-14: the application database account has INSERT-only rights on the audit table (proposed); every transition writes its audit row in the same transaction (rule TX, response spec section 1) | AS-14 by M5 (W9) | C1, C5 |
| TM-09 | Denial of service through large uploads or repeated jobs | Very large files or repeated analysis jobs exhaust disk, memory, worker or HPC capacity. | Platform unavailable; analysis delayed | 2 | 3 | 6 High | C-18 (proposed) | AS-02 by M5 (W9); AS-17 by M9 (W20) | C1, C2 |
| TM-10 | Session theft, credential compromise or session misuse | A token is stolen or fixed, a password is guessed, or a cross-site request rides on a valid session (including the WebSocket). | Attacker acts as a legitimate user | 2 | 3 | 6 High | C-02, C-03, C-19 (proposed); Part A2.1–A2.8 (opaque server-side token, `HttpOnly` and `SameSite=Strict` cookie, new token on login, revocation, `Origin` checks for CSRF and WebSocket) | AS-12 by M5 (W9) | C5 |
| TM-11 | Unsafe scenario selection, or a simulated action mistaken for a real one | The system selects a wrong or unsafe scenario on expiry, selects twice, or a simulated action is shown as if it changed a real system. | Wrong response record; false belief that a real host was changed | 2 | 3 | 6 High | C-13; server-owned deadline; exactly-once expiry; `SIMULATED` label (NFR-SF-07) | AS-09, AS-10 by M4 (W4), with AS-10 fake-clock tests in W2 (response spec section 7); AS-19 by M5 (W9) | C5 |
| TM-12 | Exposure of credentials or secrets; dependency or configuration weakness | A secret is committed or baked into an image, or a vulnerable or unpinned dependency or an unsafe default is shipped. | Credential leak; exploitable component | 2 | 3 | 6 High | C-06 (gitleaks in CI), C-20 (proposed), pinned dependencies, `.env` git-ignored | AS-13 (first version) and AS-18 by M5 (W9); AS-13 (final) by M6 (W14) | C1 |
| TM-13 **(proposed new ID, needs team agreement)** | Unauthorized response-action execution | Someone triggers or approves a (simulated) response without the right role, outside the 60-second window, or with a scenario that is not in the catalogue. | An unauthorized decision is recorded and executed (simulated) | 2 (proposed) | 3 (proposed) | 6 High (proposed) | C-04 server-side role check on the decision endpoint; catalogue check (FR-44); conditional window update (response spec section 7); refusal audited (FR-39) | AS-10 by M4 (W4), with fake-clock tests in W2; AS-12 by M5 (W9) | C5 |

**Why TM-11 does not already cover TM-13.** TM-11 is about the system's own scenario selection and labelling. TM-13 is about who may make a response decision, and when.

## B3. Mapping from the Week 1 task threats

| Week 1 task threat | TM IDs |
|---|---|
| Unauthorized access | TM-02 |
| Privilege escalation | TM-03 |
| Session theft | TM-10 |
| Malicious logs | TM-01 (malicious files); TM-06 (malicious content aimed at the LLM); TM-09 (volume) |
| Prompt injection | TM-06 |
| Unauthorized response execution | TM-13 (who may decide); TM-11 (what the system selects) |
| Credential and secret exposure | TM-12 (secrets in code, images or configuration); TM-10 (user credentials) |
| Audit tampering | TM-08 (audit records); TM-04 (evidence and incident records) |

## B4. Residual risks

Controls C-16 to C-20 are proposed, and TD-8 decides them at W6. If TD-8 does not approve a control, the threats it covers become **accepted residual risks of the prototype**. They must be listed as residual risks in the final report, not described as "not in the requirements".

| Control if not approved | Threats that become residual risks |
|---|---|
| C-16 | TM-04 |
| C-17 | TM-07 |
| C-18 | TM-09 (and the size limit part of TM-01) |
| C-19 | TM-10 (password guessing without rate limiting or lockout) |
| C-20 | TM-12 |

Two further known residual points:

- **Lockout can be abused (A2.11).** Anyone who knows a username can lock that account by sending failed logins. This is an **accepted residual risk** of the prototype, because the effect is limited:
  - the lockout applies to one username only, not to an IP address or to the whole system;
  - it lasts only 15 minutes;
  - every failure and every lockout is audited (C-14), so abuse is visible;
  - the System Administrator can unlock the account at once (part of "Manage users and roles", A3).
- **Ratings stay at their original values.** TM-03 and TM-10 keep their original ratings until AS-12 and AS-13 pass (B1).

## B5. Out of scope

- **Real endpoint, firewall or account changes.** None exist: every response action is simulated (NFR-SF-01, C-13).
- **MFA,** unless the supervisor asks for it (C-19).
- **Physical and host-OS security of the lab machine.**

---

# Part C: Open questions

Each item below is **(proposed, needs team agreement)**. The default applies until the team decides otherwise.

| # | Question | Proposed default | Decided by |
|---|---|---|---|
| 1 | Server-side sessions or JWT? | Server-side opaque sessions; only the token's SHA-256 hash is stored (A2.1) | Team, before T2-15 |
| 2 | Session lifetimes? | 30 minutes idle, 8 hours absolute (A2.3) | Team, before T2-15 |
| 3 | Cookie flags? | `icd_session`; `HttpOnly`; `Secure`; `SameSite=Strict`; `Path=/`; no `Domain` (A2.2) | Team with C4, before T2-15 |
| 4 | Password policy? | 12 to 128 characters, no composition rules, common-password list (A2.10) | Team |
| 5 | Rate-limit and lockout numbers? Is lockout abuse acceptable? | 5 failures per username per 15 minutes, then a 15-minute lockout; System Administrator can unlock; abuse accepted as a residual risk (A2.11, B4) | TD-8 at W6 (C-19) |
| 6 | One role per user? | Yes, in the MVP (A2.13) | Team |
| 7 | The OD-24 proposal cells in A3 | As listed in A3; deny by default for everything not listed | OD-24 at W5 |
| 8 | Who confirms `Resolved` → `Closed` (T13)? | Not decided; deny by default until OD-24 | OD-24 at W5 |
| 9 | Accept TM-13 as a new threat ID with L 2, I 3? | Yes (B2) | Team |
| 10 | Notifications versus the "receive escalations" permission | Not a conflict: a dashboard notification goes to both SOC Analyst and SOC Manager at freeze start (FR-26, FR-43); only the SOC Manager gets the escalation view (D7.2). OD-24 confirms (A3, note 3). | OD-24 at W5 |
| 11 | An INSERT-only database account for the audit table? | Yes: the application account can insert audit rows but cannot update or delete them (TM-08) | C1 with C5 |
| 12 | Same origin for dashboard and API? | Decided by C1, needs C4 agreement: `web` reverse-proxies `/api` and `/ws` to `api`; cookie stays `SameSite=Strict`, the `Origin` check allow-lists a single origin, no CORS. C1 implements it before T2-15 (A2.14). | C4 agreement |

---

# Traceability

| Section | Source IDs |
|---|---|
| A1 Requirements | NFR-S-01, NFR-S-02, NFR-S-03, NFR-S-04, C-01 to C-06, C-14, C-19, FR-39, TD-8, TD-12 |
| A2.1 Server-side sessions | C-01, C-03, NFR-S-01 |
| A2.2 Cookie | C-05, NFR-S-03, TM-10 |
| A2.3 Expiry | C-03, NFR-S-01 |
| A2.4 Login | C-02, C-14, NFR-S-04, TM-10 |
| A2.5 Logout | C-03, C-14 |
| A2.6 Invalidation | C-03, TM-03, TM-10 |
| A2.7 CSRF | C-04, C-14, FR-39, TM-10 |
| A2.8 WebSocket | C-01, C-03, TM-10 |
| A2.9 Argon2 | NFR-S-01, C-02 |
| A2.10 Password policy | C-02 |
| A2.11 Rate limiting and lockout | C-19, TD-8, C-14 |
| A2.12 No hardcoded credentials | C-06, NFR-S-03, TM-12 |
| A2.13 One role per user | C-04, TM-03 |
| A2.14 Same origin | C-04, C-05, TM-10 |
| A3 Roles and permissions | D7.1, D7.2, D7.5, D1.2, OD-24, OD-17, C-04, C-14, FR-26, FR-35, FR-39, FR-43, NFR-S-02 |
| B2 Threat table | Roadmap gates M4, M5, M6, M9; TM-01 to TM-13, C-01 to C-14, C-16 to C-20, AS-02, AS-04, AS-05, AS-06, AS-08, AS-09, AS-10, AS-12 to AS-15, AS-17 to AS-19, OD-16, NFR-SF-06, NFR-SF-07, FR-39, FR-44 |
| B4 Residual risks | C-16 to C-20, TD-8 |
| B5 Out of scope | NFR-SF-01, C-13, C-19 |
