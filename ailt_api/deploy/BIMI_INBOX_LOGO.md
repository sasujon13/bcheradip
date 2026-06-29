# Gmail inbox logo (circle avatar next to sender)

The **HTML email template** shows your app icon + wordmark **inside the email body**.

The **circle avatar in Gmail’s inbox list** (like Brevo’s “B”) is **not** controlled by the email HTML. Gmail uses:

1. **First letter of display name** — `Cheradip` → **C** in a colored circle (default today)
2. **BIMI** (Brand Indicators for Message Identification) — your logo instead of C

---

## What we did in the email template

- **App icon** (`ic_launcher_foreground.png`) → circular avatar in header (Brevo-style)
- **Cheradip wordmark** (SVG → PNG) → logo text under the avatar
- Embedded as **inline PNG** (`cid:`) because **Gmail blocks SVG**

Assets:

```
ailt_api/app/assets/email/cheradip-avatar.png    # Android launcher
ailt_api/app/assets/email/cheradip-wordmark.png  # from cheradip.svg
```

Rebuild PNGs after logo changes:

```bash
bash ailt_api/scripts/build-email-assets.sh
```

---

## BIMI — custom logo in Gmail inbox (optional)

Requirements:

1. **DMARC** on `cheradip.com` with `p=quarantine` or `p=reject`
2. **Verified domain** in Brevo (already done)
3. **SVG logo** hosted at HTTPS (SVG Tiny P/S format)
4. **DNS TXT** record:

```
Host: default._bimi.cheradip.com
Value: v=BIMI1; l=https://cheradip.com/.well-known/bimi/logo.svg;
```

5. Host logo file at that URL (copy from `app/assets/email/cheradip.svg` or a simplified square version)

Gmail may also require a **Verified Mark Certificate (VMC)** for full logo display — see [Google BIMI guide](https://support.google.com/a/answer/10908888).

Timeline: DNS + DMARC can take days; Gmail BIMI rollout is gradual.

---

## Brevo sender branding

In Brevo dashboard check **Senders & IP** → your domain → any **brand logo** option for transactional mail. Some plans show Brevo branding on `@smtp-brevo.com` test sends; production From `noreply@cheradip.com` uses your domain reputation.

---

## Verify template v3 on server

```bash
curl -s http://127.0.0.1:8790/api/ailt/health | python3 -m json.tool
# "email_template": "otp-html-v3"

bash scripts/test_smtp.sh your@gmail.com
# MIME check: ... 2 inline PNG(s) — OK
```

In Gmail → **Show original** → search for `otp-html-v3` and `Content-ID: <cheradip-avatar>`.
