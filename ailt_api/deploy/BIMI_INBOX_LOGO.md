# Gmail inbox logo next to noreply@cheradip.com

## Two different places

| Where | What you see | Controlled by |
|-------|----------------|---------------|
| **Gmail inbox list** — circle next to sender name | Brevo shows **B**, you see **C** today | **BIMI** (not email HTML) |
| **Inside the email body** | Cheradip wordmark in the header | HTML `<img src="https://...">` |

**You cannot set the inbox sender avatar from the OTP email template.**  
Brevo’s **B** appears because Brevo has BIMI configured for `brevo.com`. For `noreply@cheradip.com`, Gmail shows the first letter of the display name (**C** from “Cheradip”) until you complete BIMI for `cheradip.com`.

---

## What you need for inbox logo (your app icon)

Gmail requires **BIMI** with a **certificate** (not just a DNS record + PNG).

### Prerequisites (free — check first)

```bash
# SPF + DKIM — already done via Brevo domain verification
dig TXT cheradip.com +short | grep spf
dig TXT mail._domainkey.cheradip.com +short

# DMARC must be enforced (p=quarantine or p=reject, NOT p=none)
dig TXT _dmarc.cheradip.com +short
```

If DMARC is `p=none`, upgrade it before BIMI. Example:

```
Host: _dmarc.cheradip.com
Type: TXT
Value: v=DMARC1; p=quarantine; rua=mailto:admin@cheradip.com; adkim=s; aspf=s
```

Wait until outgoing mail from `noreply@cheradip.com` passes DMARC consistently.

### Certificate (paid — required for Gmail)

| Type | Trademark needed? | Gmail inbox logo | Blue checkmark | Approx. cost |
|------|-------------------|------------------|----------------|--------------|
| **CMC** (Common Mark Certificate) | No — 12+ months public logo use | Yes | No | ~$650–950/year |
| **VMC** (Verified Mark Certificate) | Yes — registered trademark | Yes | Yes | ~$1,400+/year |

**Recommended for Cheradip:** **CMC** from [DigiCert](https://www.digicert.com/vmc/) (no trademark).

Submit your **app icon** (`ic_launcher_foreground.png`) — square, 96×96 minimum. DigiCert validates and produces the BIMI-compliant SVG.

Source file in this repo:

```
ailt_api/app/assets/email/cheradip-avatar.png
```

### After certificate is issued

1. Host the **SVG logo** at HTTPS, e.g.  
   `https://cheradip.com/.well-known/bimi/logo.svg`

2. Host the **certificate PEM** at HTTPS, e.g.  
   `https://cheradip.com/.well-known/bimi/cert.pem`

3. Add DNS TXT record:

```
Host: default._bimi.cheradip.com
Type: TXT
Value: v=BIMI1; l=https://cheradip.com/.well-known/bimi/logo.svg; a=https://cheradip.com/.well-known/bimi/cert.pem;
```

4. Nginx — add inside `cheradip.com` server block (see `deploy/nginx-bimi-wellknown.conf`):

```nginx
location /.well-known/bimi/ {
    alias /home/sasha/apps/cheradip/bcheradip/ailt_api/deploy/bimi/;
    default_type application/octet-stream;
    add_header Access-Control-Allow-Origin *;
}
```

5. Timeline: certificate validation 5–10 days; Gmail may take **days to weeks** after DNS + DMARC are correct.

---

## Body images not showing in Gmail

Separate from inbox avatar. If the **wordmark inside the email** is missing:

1. **Display images** — Gmail may hide remote images until you tap **“Display images below”** or enable **Always display images from cheradip.com**.

2. **Deploy PNGs** — nginx serves stable URLs (Angular alone is not enough):

```bash
bash ailt_api/scripts/build-email-assets.sh
# Add ailt_api/deploy/nginx-email-assets.conf to nginx (before location /)
sudo nginx -t && sudo systemctl reload nginx
curl -sI https://cheradip.com/assets/email/cheradip-wordmark.png | head -1
```

**Why Angular `/assets/email/` fails:** production build renames PNGs with content hashes and missing paths fall back to `index.html` (page title "Cheradip", no image).

**Immediate fallback** (no nginx change): in `ailt_api/.env`:

```env
EMAIL_ASSETS_BASE_URL=https://cheradip.com/ailt/api/assets/email
```

3. **Optional `.env`** (usually not needed — default is already main site):

```env
EMAIL_ASSETS_BASE_URL=https://cheradip.com/assets/email
```

4. In received mail → **Show original** → search for `cheradip-wordmark.png` and confirm the URL is `https://cheradip.com/assets/email/...`

---

## Checklist summary

- [ ] DMARC `p=quarantine` or `p=reject` on cheradip.com  
- [ ] Order **CMC** from DigiCert with app icon PNG  
- [ ] Host logo.svg + cert.pem at `/.well-known/bimi/`  
- [ ] Publish `default._bimi.cheradip.com` TXT record  
- [ ] Deploy fcheradip so body wordmark PNG is at `/assets/email/`  
- [ ] Wait for Gmail to show logo in inbox (not instant)

There is **no Brevo dashboard setting** that replaces BIMI for your own domain’s inbox avatar.
