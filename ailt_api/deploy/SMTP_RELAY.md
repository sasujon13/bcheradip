# SMTP — deliver from noreply@cheradip.com

**Primary guide:** [MAIL_NOREPLY_CHERADIP.md](./MAIL_NOREPLY_CHERADIP.md)

| Setting | Value |
|---------|--------|
| Visible From | `noreply@cheradip.com` |
| SMTP auth | user **`admin`**, port **587**, TLS |
| App connects to | `127.0.0.1:587` → Postfix → OpenDKIM → internet |

**Never use** `SMTP_PORT=25` in `ailt_api/.env` — Gmail/Yahoo return `550 5.7.1` for direct VPS send.

---

## Requirements for Gmail / Yahoo / Outlook

1. DNS: `mail.cheradip.com` A, MX, SPF, DKIM (`mail._domainkey`), DMARC  
2. Postfix submission **587** + SASL user `admin`  
3. OpenDKIM running (`fix-opendkim.sh`)  
4. VPS **PTR** (reverse DNS) → `mail.cheradip.com`  

Scripts on the server:

```bash
sudo bash deploy/scripts/fix-postfix-587.sh
sudo bash deploy/scripts/setup-smtp-admin-user.sh
./scripts/test_smtp.sh your@gmail.com
```

---

## Fallbacks

| Method | From address | When |
|--------|--------------|------|
| Postfix 587 + DNS | `noreply@cheradip.com` | **Preferred** |
| Gmail App Password | `@gmail.com` | Quick test — [SMTP_GMAIL.md](./SMTP_GMAIL.md) |
| Google Workspace | `noreply@cheradip.com` | Paid custom domain via Google |
