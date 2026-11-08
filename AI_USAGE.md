# AI usage

## Tools used

- **Claude Code** (Anthropic), running Claude Opus 5.5. I used it as a coding agent in my
  terminal. For the build, it ran up to four agents: one built the foundation first, then three
  worked in parallel, each on its own git branch.

## What AI helped with

Most of it. I want to be plain about that.

- **Reading the brief and planning.** Claude turned the 18-page PDF into a requirement checklist
  and proposed the design. I made the main decisions:
  - Flask over Django or FastAPI, so every line is visible and easy to explain.
  - Local MySQL first, with hosting optional.
  - The repo layout.
  - How the work was split.
- **Writing the code.** Models and migrations, the services (pricing, orders, stock, catalog,
  reports, CSV import), routes, templates, the order form JavaScript, the seed script and the
  SQL queries.
- **Writing the tests and the docs.** The README, `docs/architecture.md`, `docs/api.md` and the
  debugging explanation.
- **Git.** The three features (`feature/rest-api`, `feature/reports-csv-import`,
  `feature/web-ui`) were built on their own branches and merged into `main` with `--no-ff`. One
  CSS merge conflict was resolved by hand. The agents committed their work in batches, so many
  commit timestamps sit close together.

## Example prompts

1. *"What do they want from us? What kind of tech stack are we using? What's the fastest route of
   building it? How do we build it from core engineering skills, like first-principles thinking?"*
   This was my opening prompt, to understand the assignment before any code.
2. *"Spin up to 4 agents max … build me the whole thing … and at the end just update the docs
   fully."* This started the build.
3. To the agent building the order logic: *"Confirm/cancel exactly per architecture.md: one
   transaction; `with_for_update()` on the order row first; lock products sorted by id; any
   shortage → nothing changes."* The design came first and the code was written to it.

## How the generated code was checked

- **Tests on a real MySQL database, not SQLite.** SQLite has no row locks, so a concurrency test
  there would prove nothing. 277 tests cover every scenario the assignment lists, plus every
  API error status.
- **The concurrency test was checked against itself.** It was run once with the
  `SELECT ... FOR UPDATE` lock removed. It failed by selling 8 units from a stock of 5, which
  shows the test really depends on the lock. The lock was then put back.
- **The JavaScript was checked in headless Chrome.** An agent wrote and ran a script that drove
  headless Chrome against the running app and the real API, in 46 checks. They covered product
  lookup, adding and removing rows, live totals for the PDF example, validation messages, save,
  edit, confirm, cancel, the stock shortage message, CSV import and the report pages. The script
  was a one-off check, kept outside the repo, so it isn't committed.
- **The five SQL queries** were run against the sample data, and a test runs each one.
- **Every README claim was checked against the code** before committing. Two were wrong and were
  fixed: it said the UI shows a ₹ sign (it doesn't), and it overstated where the tests are
  labelled.

## Issues found and corrected

- **A stale snapshot in the order confirm.** Under MySQL's default isolation level
  (`REPEATABLE READ`), the transaction starts when the logged-in user is loaded. After locking an
  order, its items could then be read from that older snapshot. The fix was to make the
  connection use `READ COMMITTED`, so reads after the lock see the latest committed data. The row
  locks are what keep stock correct.
- **Logged-out API calls got the wrong error.** They returned a CSRF error (400) instead of
  "not logged in" (401), because the CSRF check ran before the login check. The fix was to
  register the login check first.
- **A test passed for the wrong reason.** Flask-Login caches the current user in `g`. In a test
  that logged in two different users in one app context, the second request reused the first
  user. That would have hidden a real permission bug. A test hook now clears the cache on each
  request.

## Review round

After the build, two independent review agents audited the whole submission. They found the
problems below. All were fixed, and each code fix has a regression test.

- **An open redirect.** The login page's `?next=` check could be passed with a tab or a
  backslash (`/<tab>/evil.example`), which browsers read as another site.
- **500 errors on big numbers.** An order line or total too large for `DECIMAL(12,2)`, a stock
  adjustment too large for a MySQL `INT`, and huge page numbers all crashed. They now get a clear
  message, or the page number is clamped. Numbers must also be plain ASCII digits now.
- **CSV import crashed on accented codes.** MySQL treated `CAFE-1` and `CAFÉ-1` as the same code
  and Python didn't. Product codes now ignore case but not accents, in the database too.
- **Confirm accepted a draft whose customer or product had been deactivated since.** It now
  refuses with a 409.
- **Smaller ones:** a delete racing a new order gave a 500; `%` and `_` in the search box acted
  as wildcards; reports formatted money through a float; there was no upload size limit and no
  `SameSite` on the login cookie; login timing could reveal which emails exist; the app started
  without a `SECRET_KEY`; `calculate_total` refused `Decimal` and accepted NaN and infinity.
- **Docs that weren't true.** `sql/schema.sql` couldn't be loaded by hand, the README said where
  the Part 12 tests are labelled but missed one, and it overstated the pinned and supported
  versions. These were corrected.
