# CWE Vulnerability Explainer

Paste a code snippet, get back a list of suspected security problems, each one
checked against a few local rules before you see it.

The model call is the easy part. The part I spent time on is what happens after
it. LLMs make up CWE numbers that look plausible, point at line 40 of a 15-line
file, and hand you JSON wrapped in markdown fences. They also label everything
with OWASP categories from the 2021 edition, which is no longer current. So the
model's answer gets treated as untrusted input.

There's a model dropdown so you can run the same snippet through a strong model
and a weak one and see what changes.

---

## Setup

### With uv

```bash
# install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

cp .env.example .env
# put your key in .env

uv sync

# check which models your key can actually reach
uv run list_models.py
uv run list_models.py claude    # filter by substring

uv run app.py
```

Then open http://localhost:7860.

### With Docker

`uv.lock` has to exist before you build, since the Dockerfile uses
`uv sync --frozen`. Run `uv lock` once on the host and commit the lockfile.

```bash
docker build -t cwe-explainer .
docker run --rm -p 7860:7860 --env-file .env cwe-explainer
```

The key goes in at runtime. To check it isn't in the image:

```bash
docker run --rm cwe-explainer env | grep -i duke   # should print nothing
```

### Configuration

Everything comes from the environment. Nothing is hardcoded.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DUKE_API_KEY` | **yes** | (none) | Gateway API key. The app exits with a clear message if it's missing. |
| `DUKE_BASE_URL` | no | `https://litellm.oit.duke.edu/v1` | OpenAI-compatible endpoint. |
| `MODEL_NAME` | no | `claude-sonnet-5` | Which model is preselected in the dropdown. |
| `PORT` | no | `7860` | Port to bind. The address is always `0.0.0.0`. |

### Running it somewhere else

The Dockerfile runs as UID 1000, exposes 7860, and binds `0.0.0.0`, so the same
image should work on a Hugging Face Docker Space without changes. Put
`DUKE_API_KEY` in the Space secrets, not the variables.

---

## What the validation actually checks

`validate_findings()` in `app.py` returns two lists: findings that passed, and
findings that got dropped along with why. Each candidate goes through:

**1. Parsing.** Code fences get stripped, and if the model buried the array in
prose the widest `[...]` or `{...}` span is pulled out. A response that never
parses is reported as a parse failure instead of taking the app down. An array
nested under `findings` / `vulnerabilities` / `results` also works.

**2. Schema.** All seven fields have to be there (`vulnerability_type`,
`cwe_id`, `owasp_category`, `severity`, `line_numbers`, `explanation`,
`remediation`) with the right types.

**3. CWE tier.** The ID gets normalized (`89`, `cwe_89`, `CWE 89` all become
`CWE-89`), then sorted into one of three buckets:

- On my curated allowlist of ~57 entries. Accepted, relabeled with the official
  MITRE name instead of whatever the model called it.
- Not on the allowlist but in `CWE_TO_OWASP_2025`. Accepted, flagged as
  unverified. It's a real CWE, but I haven't checked its name or severity.
- In neither. Rejected as a probable hallucination.

That middle bucket exists because of a bug I hit while testing. The original
version rejected anything off the allowlist, and it threw away a correct
CWE-328 finding for MD5 token generation. A 57-entry list I picked by hand is a
subset of what exists, not a definition of it.

**4. Severity.** Has to be `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `INFO`.

**5. Line numbers.** Every cited line has to exist in the snippet. Strings like
`"12"` get coerced; anything else is rejected. The prompt sends numbered lines
so the model has something real to cite, and this catches it when it ignores
them anyway.

**6. Duplicates.** If every (CWE, line) pair a finding claims was already taken
by an accepted finding, it gets dropped.

**7. OWASP category.** The model's category gets compared against the official
Top 10:2025 mapping. On a mismatch the finding is **corrected, not rejected**.
The vulnerability is real, the label was just wrong. The original claim is kept
and a note explains what happened.

This one fires constantly. OWASP renumbered in the 2025 edition: Injection went
from A03 to A05, Cryptographic Failures from A02 to A04, and SSRF lost its own
slot and got folded into A01. Every model I tested still uses the 2021 numbers,
because they were trained before the new edition came out. The note reads
differently depending on whether the model gave a stale category or an invented
one, since those are different problems.

The comparison only looks at the `A01` to `A10` code, not the full string, so
en dash vs hyphen or a missing year doesn't count as a mismatch.

One deliberate choice: the prompt doesn't include the allowlist and doesn't tell
the model which OWASP edition to use. Doing either would hide these errors
rather than surface them, and surfacing them is the whole point.

The summary line at the top shows what the model returned, what passed, what
carried an unverified CWE, what got filtered, and how many categories were
corrected. The **Filtered out** tab shows each dropped finding with its reason.

### Where the OWASP mapping comes from

`cwe_owasp_map.py` is generated, not typed by hand. `build_mapping.py` pulls the
ten official Top 10:2025 category pages, parses the "List of Mapped CWEs"
section on each, and writes out a 249-entry dict.

```bash
uv run build_mapping.py
```

Scraping instead of transcribing means every entry traces back to the source and
I can regenerate the table when OWASP revises it. The script prints a count per
category as a check. A01 should be 40, A05 37, A07 36, matching the pages.

A CWE that isn't in the mapping gets passed through unchanged. The Top 10
doesn't cover every CWE (resource exhaustion, ReDoS, most memory-safety issues
have no 2025 category) so a gap in the table isn't evidence of a hallucination.

### Gateway parameter quirks

Some of the newer reasoning models reject `temperature` and want
`max_completion_tokens` instead of `max_tokens`. Rather than hardcoding which
model needs what, `call_model()` sends the preferred parameters, reads the 400
response to find out which one was refused, swaps or drops it, and retries. Any
adaptation shows up as a note under the summary.

### Model names

The dropdown is a hardcoded list. Gateways add and rename models constantly, so
check against your own key before trusting any of these:

```bash
uv run list_models.py
```

Worth knowing: the naming is inconsistent. Newer models are lowercase and
hyphenated (`gpt-5.4-nano`), but several older OpenAI ones are registered with
spaces and capitals (`GPT 4.1 Nano`). Getting it wrong gives you a 403, not a
404, which makes a typo look like a permissions problem.

If `MODEL_NAME` points at something outside the list, it gets added so the
configured default is always selectable.

---

## Limitations, please read this

**This is a triage aid for a human reviewer. It is not a scanner and it doesn't
replace SAST tooling.**

- **It will miss things.** Including serious things. A clean result here means
  nothing at all. It is not evidence that code is safe.
- **It will flag things that aren't real.** Passing validation means a finding
  is well-formed and cites a real CWE on a real line. It does not mean the
  vulnerability exists. The checks are structural. They never look at whether
  the finding is correct. A confident, perfectly formatted finding can be
  completely wrong.
- **Unverified findings are only structurally checked.** A real CWE that isn't
  on my allowlist gets accepted with its name and severity taken from the model.
  The flag is there to tell you to check it yourself.
- **The OWASP correction is mechanical.** It fixes the label when the CWE is in
  the mapping. It can't tell you whether the CWE was the right call in the first
  place. A mislabeled vulnerability just gets a confidently corrected category.
- **It only sees the snippet.** No surrounding project, no call graph, no
  dependency versions, no data flow. Insecure defaults set elsewhere, taint
  crossing module boundaries, vulnerable transitive dependencies are all
  invisible.
- **It's not deterministic.** Same snippet, same model, different runs, different
  findings.
- **Severity ratings are guesses.** They aren't anchored to exploitability
  analysis or CVSS.
- **Don't paste secrets or proprietary code** into a hosted deployment. Snippets
  go to the gateway and on to the model provider.

Use it to generate leads for a human to check, alongside actual SAST tooling
(Semgrep, CodeQL, Bandit), dependency scanning, and someone who knows the
codebase.

---

## AI assistance

Per the course citation policy.

I built this on September 4, 2026, in a session with **Claude Opus 5**
(Anthropic, claude.ai) starting around 12:30 PM.

**What the model wrote:** the initial scaffold (`app.py`, `Dockerfile`,
`pyproject.toml`, `.dockerignore`, `.gitignore`, `.env.example`,
`list_models.py`, and a first draft of this README including the Limitations
section) from a spec I gave it covering what the validation had to check, the
environment-only config constraint, and the gateway parameter handling. Later
in the same session it also wrote `build_mapping.py`, `check_owasp_mapping()`,
and the three-tier CWE check, to designs I specified, and revised the
Limitations section to cover the unverified-CWE tier and the OWASP correction.

**What I decided and did:**

- Picked the problem and the framing. I want to work in application security,
  and this is the first pass I'd actually run on someone else's code: a tool
  that doesn't trust its own model.
- Went with OWASP Top 10:**2025** rather than 2021, which is what most tooling
  still assumes, after checking that 2025 is the current release.
- Decided to scrape the CWE to OWASP table from the official pages instead of
  transcribing it, so every entry traces back to a source and I can regenerate
  it later. Checked the output against the published per-category counts
  (A01 = 40, A05 = 37, A07 = 36).
- Decided a stale OWASP category should **correct** a finding rather than
  reject it, and that a stale-edition answer should read differently from an
  invented one.
- Decided the comparison should use the A01 to A10 code alone so punctuation and
  wording differences don't trigger false mismatches.
- Found the tier bug by testing. The original allowlist check threw away a
  correct CWE-328 finding as a hallucination. Worked out why (I was treating a
  57-entry list I'd picked by hand as a definition of what exists) and specified
  the three-tier fix.
- Chose and verified the models against the gateway, including working out that
  the older OpenAI models use spaced, capitalized names that don't match the
  newer convention.
- Ran all the container builds, the end-to-end testing, and the secret-handling
  check.
- Reviewed and signed off on the Limitations section, which the model drafted.
  The framing it describes, that this is a triage aid and a clean result proves
  nothing, is the position I want the tool to take.
