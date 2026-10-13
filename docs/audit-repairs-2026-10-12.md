# Approved website audit repairs: 1–26

The existing URLs, Bearer APIs, main/shared header styles and independent AILT API are preserved. Financial tests use disposable SQLite databases, not customer accounts. Existing duplicate/misplaced database tables have not been deleted.

## Repair index

| Audit | Implemented change |
|---|---|
| 1 | Withdrawal requests reserve both reference earnings and their equivalent main-wallet Coins. Cancellation/rejection releases the reservation once. Legacy unreserved withdrawals cannot be silently approved. |
| 2 | Database routers defer correctly and only migrate each model to its owning database. |
| 3 | Checkout locks/rechecks the cart; its token uniquely identifies the resulting order. Repeated checkout returns that order without another debit. |
| 4 | Committed main-wallet operations form an idempotent ledger. Commerce acknowledges a wallet payment only after its debit commits; reconciliation can recover an interrupted acknowledgement. |
| 5 | Customer payment submissions always start pending. Duplicate submissions are reused; paid, cancelled, completed and refunded orders reject new payment submissions. |
| 6 | Order/payment transitions are validated. Cancellation/return restores stock once; wallet refunds restore the main balance and the consumed reference portion once. |
| 7 | Django order/payment forms and actions use the same domain handlers as APIs. Immutable order items/inventory history and computed financial records cannot be freely edited. Sensitive raw-table writes are disabled. |
| 8 | Raw views check database ownership and model permissions. Unregistered tables/content jobs/server settings require superuser access. AILT and Agent databases are read-only; credential columns are masked. |
| 9 | Digital access requires a purchased digital book variant, not merely a hard copy of the same product. |
| 10 | Uploaded book files are stored outside public media. Samples/video files have an explicit public endpoint; paid manuscripts require the protected download endpoint. |
| 11 | Public question lists mask locked answers/explanations. Unlocking fetches the authorized solution from the server; customer settings cannot grant Coins or unlock rights. Attempt answer snapshots are not exposed through settings. |
| 12 | Introductory Free grants cannot be restarted through another Free track or an exhausted allowance. Paid access does not leave introductory Free access active. |
| 13 | Student-package Study benefits work for Teacher/Job Seeker accounts too; the purchased package family, not account type, determines entitlement. |
| 14 | Unlock identities include database, subject table and question ID. The server determines MCQ/CQ price. Existing server-paid legacy IDs bind once to a subject without being charged again. |
| 15 | Date parsing is imported and covered by progress/report tests. Bengali answer-marker comparison also uses UTF-8 bytes, avoiding a previously untested grading error. |
| 16 | The attempt endpoint enforces exam availability dates. Attending exams remains free and does not apply Study-package source filters. |
| 17 | Each attempt freezes the shown question list and answer key; submissions and duplicate replies use this snapshot rather than the current mutable exam set. |
| 18 | New exam results use permanent records with optional pagination. Existing JSON history remains readable; records are no longer truncated at 2,000. Already-deleted historical records cannot be reconstructed. |
| 19 | Old student exam/tutor URLs redirect to the current working exam player and curriculum-aware tutor. |
| 20 | Add to cart increments quantity; explicit quantity controls send a set operation. Checkout and cart edits share the cart lock. |
| 21 | Book metadata synchronization no longer restores sold stock. The storefront shows authoritative variant stock. Subsequent inventory adjustments belong to Product Variant/inventory management. |
| 22 | Books have Load more pagination. Network failures preserve the saved cart, and cart additions update the shared header counter. |
| 23 | Liked/hidden state is isolated by account and subject. Liked snapshots sync through account settings. Account switches do not expose another user's saved state. Legacy hidden IDs bind to one subject. |
| 24 | Tutor-key updates lock the current customer JSON before merging, preserving concurrent wallet/progress changes. |
| 25 | All eight database sections are available. Django writes/deletes produce acknowledged per-table activity; unresolved work retains its action count. The external-table scanner detects changes made outside Django, including timestamp-less tables. |
| 26 | HTTPS Cheradip subdomains share a Secure, HttpOnly, SameSite session cookie. The frontend restores a valid first-party session before guarded navigation; legacy Bearer clients continue working. Cookie-authenticated writes enforce trusted origins. |

## Local verification

- 82 backend tests pass in disposable databases (account, packages, progress, commerce and audit regressions).
- 123 frontend tests pass, including account isolation and reused-ID unlocks.
- Development and production frontend builds pass.
- Django deployment checks pass; no missing model migrations remain.
- Live local GET checks return 200 for country, notification, question levels, exam sets, marketplace categories/products/books and Child Care health.
- Anonymous Physics question-list checks retain the 13,980-question count but mask locked answer/explanation fields.
- Read-only reconciliation finds no historical unreserved local withdrawals; no real order debits/refunds were performed by the tests.
- AILT/Agent external-table fingerprint baselines were established without modifying their source records.

## Production rollout

Back up the production databases and uploaded files before deployment. Pause wallet checkout/withdrawal writes briefly while deploying the backend and applying these additive migrations. Deploy the matching frontend so unlock requests include subject context and cart quantity controls use `operation: set`.

From the backend directory, with its environment activated:

```text
python manage.py migrate cheradip --database default --noinput
python manage.py migrate ecommerce --database ecommerce --noinput
python manage.py check --deploy
python manage.py protect_ebook_files
python manage.py reconcile_commerce_wallets
```

`protect_ebook_files` first reports old public assets without moving anything. After reviewing the report, `--apply` copies and verifies the files in private storage, then archives the public originals outside public media. The default private directory is `bcheradip/private_ebooks`; set `PRIVATE_EBOOK_ROOT` in the deployment environment if a different location is required. Never expose this directory using nginx/media aliases. Back it up separately. Existing third-party ebook URLs depend on that provider's own access controls; use privately uploaded files for protected sales.

`reconcile_commerce_wallets --apply` only acknowledges already committed ledger debits/refunds; it never charges a customer. Orders predating the ledger require review of payment evidence before any ledger migration or financial correction. For interrupted cancellation/refund stock changes, retry the validated admin action after reviewing the reconciliation report. This run did not rewrite historical balances.

Do not delete misplaced old tables after the router fix without separately verifying their contents and dependencies. Migration routing affects future operations, not historical data relocation. Missing schema columns on a remote database need these migrations: the insert-only `mysql_db_sync --l2r` does not alter existing tables. `--r2l` remains a destructive snapshot restore and is now documented accurately.

### Subdomain sessions

All public subdomains must use HTTPS, forward `X-Forwarded-Proto`, and preserve the current `/api/` proxy routes. The cookie is scoped to `.cheradip.com`, not an arbitrary third-party host. CORS allows the configured Cheradip origins and credentials. Users signed in before deployment may need one normal sign-in to establish the new cookie. SSO was regression-tested locally with simulated HTTPS hosts; actual production browser behavior still requires a deployed smoke test. The independent Android/FastAPI authentication contract is unchanged.

### Database activity markers

Django model writes/deletes are tracked automatically after successful commit. Viewing a table/changelist acknowledges its change events for that administrator. Pending withdrawals/orders/payments remain marked until resolved, even after viewing; those circles represent outstanding work, not unread messages.

Writes from external services, imports, database tools or direct SQL cannot emit Django signals. Refresh their markers using:

```text
python manage.py scan_admin_table_changes --database ailt --database extcheradip
python manage.py scan_admin_table_changes --database hsc --table YOUR_SUBJECT_TABLE
python manage.py scan_admin_table_changes
```

The first scan establishes a baseline; later scans publish a change event when a table's content differs. It reads source tables without changing them and stores only hashes/checkpoints in Cheradip. These circles count observed changes, not an exact number of externally edited rows. Opening the AILT/Agent admin tab automatically starts a non-blocking scan, limited to once per five minutes; refresh the admin page after it finishes to see newly observed changes. Run a full scan off-peak for large question databases; it reads complete tables and intentionally is not run during ordinary student page requests. No separate recurring job was installed. For direct-SQL changes to other databases, run the scanner after the changes or invoke it from the deployment's existing maintenance process.
