# Gmail blocks direct VPS send (550 5.7.1) — relay options

Your app and Postfix work. Gmail rejects IP **`163.227.144.146`** for direct delivery.

To keep **From: noreply@cheradip.com** without Brevo:

---

## Option 1 — Amazon SES (recommended)

1. [AWS SES](https://aws.amazon.com/ses/) → verify domain **cheradip.com** (add DNS TXT/CNAME they give you).
2. Create **SMTP credentials** in SES console.
3. Postfix relay (keeps `ailt_api` on `127.0.0.1:587`):

```bash
sudo postconf -e 'relayhost = [email-smtp.eu-west-1.amazonaws.com]:587'
sudo postconf -e 'smtp_sasl_auth_enable = yes'
sudo postconf -e 'smtp_sasl_security_options = noanonymous'
sudo postconf -e 'smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd'
sudo postconf -e 'smtp_tls_security_level = encrypt'

sudo bash -c 'cat > /etc/postfix/sasl_passwd <<EOF
[email-smtp.eu-west-1.amazonaws.com]:587 YOUR_SES_SMTP_USER:YOUR_SES_SMTP_PASSWORD
EOF'
sudo chmod 600 /etc/postfix/sasl_passwd
sudo postmap /etc/postfix/sasl_passwd
sudo systemctl restart postfix
```

Replace region (`eu-west-1`) with your SES region.

4. Add SES SPF to DNS: `v=spf1 include:amazonses.com ~all` (or merge with existing SPF).

---

## Option 2 — Google Workspace

- Add **cheradip.com** to Google Workspace.
- Create user or alias **noreply@cheradip.com**.
- Use `smtp.gmail.com:587` with App Password, or Postfix relay via Google.

---

## Option 3 — Finish self-hosted (may still fail on Gmail)

Required DNS (you are **missing the A record**):

| Type | Name | Value |
|------|------|--------|
| **A** | `mail` | `163.227.144.146` |
| MX | `@` | `10 mail.cheradip.com` |
| TXT | `@` | `v=spf1 ip4:163.227.144.146 a mx ~all` |
| TXT | `mail._domainkey` | from `fix-opendkim.sh` output |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@cheradip.com` |

Plus **PTR**: `163.227.144.146` → `mail.cheradip.com` (VPS panel).

Test score: [mail-tester.com](https://www.mail-tester.com)

Gmail may **still** return 550 on new VPS IPs even with perfect DNS.

---

## Current status (working)

```
ailt_api → 127.0.0.1:587 (TLS, no auth) → Postfix → internet
```

Only the **last hop to Gmail** is blocked by Google policy.
