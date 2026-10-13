# Follow-up audit repairs and administrator rollout

The staff-only manual is at `/admin/manual/`. It is linked from the Django admin home page and its header. It explains accounts and permissions, packages, wallet and recharge, marketplace orders, books, education content, institute unlocks, activity markers, and operations. It is not a public frontend route.

## Repairs completed

- Account recovery codes are purpose-bound, hashed, short-lived, rate-limited, and sent only to a previously saved contact. A recovery request cannot replace the saved email.
- Payment intake requires a server-side `TRX_INGEST_SECRET` and a matching `X-Cheradip-Ingest-Key` header. Amount/currency are validated. A unique transaction identity and wallet ledger prevent duplicate credit. Unverified historical receipts cannot activate until checked.
- Membership reads no longer treat expired paid plans as current. Renewal and teacher allowance rules are covered by tests. Numeric MCQ answer text is matched before interpreting answer markers.
- Staff commerce APIs require model/action permissions. CSV import and inventory adjustment require the permissions for both kinds of records they write. Checkout rechecks ownership, availability, prices, and replay identity; refunded payments cannot complete again.
- CSV imports reject negative/nonfinite prices, preserve existing values for blank update cells, and do not report rolled-back rows as imported. Product filters reject invalid price ranges.
- Purchase history pages through older package and product/book orders. Digital purchases allow their signed-in owner to download without re-entering a tracking token; hard-copy orders do not grant digital access.
- Institutional mobile/email fields are public again on `/institutes`; extended legacy BANBEIS records still require an account-specific paid EIIN unlock. Legacy browser lists cannot grant paid access. The institute page cancels stale page/filter responses, and year headings are based on dataset dates instead of the current year.

## Local migration and verification

The additive `cheradip` migration `0027_recovery_and_recharge_identity` has been applied to the local default database. It adds the recovery challenge, canonical recharge identity, and `verified` status. At the time of migration, there were 44 recharge rows, including 38 pending rows. Those 38 rows remain pending and unverified; no customer balance was changed. Staff must validate a pending receipt against the payment provider's official record before marking it verified. Do not bulk-approve them.

Tests use disposable databases: the full Django suite passes (317 tests, 10 skipped) and the Angular suite passes (124 tests). The Angular development build, Django deployment check, migration consistency check, and diff whitespace check pass. A production browser smoke test and remote migration are still required when deploying.

## Production prerequisites

1. Back up databases, media, and private eBook storage. Keep the matching frontend/backend versions together. Apply `python manage.py migrate cheradip --database default --noinput` and existing eCommerce migrations on their owning databases.
2. Configure a strong, independently generated `TRX_INGEST_SECRET` only on the Django server and trusted payment-intake sender. The sender must place the same value in `X-Cheradip-Ingest-Key`. Do not put it in frontend assets, source control, an admin note, or a public page. If absent, payment intake intentionally refuses requests; existing pending payments must be checked manually.
3. Run `python manage.py check --deploy`. Smoke-test sign-in/recovery, recharge with a test receipt, package renewal, customer checkout and order history, digital download, institute unlock, and the staff-only `/admin/manual/` route. Do not use a real customer's wallet for tests.
4. Review older EIIN unlock claims against payment/support evidence before restoring an entitlement. The former browser-stored list is not reliable proof of payment. Preserve wallet-operation evidence when making a correction.
5. Run the read-only `reconcile_commerce_wallets` and `protect_ebook_files` reports before using either `--apply` mode. The earlier audit rollout instructions are in `audit-repairs-2026-10-12.md`.

No remote deployment, commit, push, refund, or live wallet debit was performed for this follow-up.
