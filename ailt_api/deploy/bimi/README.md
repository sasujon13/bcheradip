# BIMI files for Gmail inbox sender logo

After you receive a **Common Mark Certificate (CMC)** from DigiCert:

1. Copy DigiCert's validated `logo.svg` here (replace `logo.svg`)
2. Copy the certificate chain PEM here as `cert.pem`
3. Apply nginx config: `deploy/nginx-bimi-wellknown.conf`
4. Add DNS TXT at `default._bimi.cheradip.com` (see `BIMI_INBOX_LOGO.md`)

Until `cert.pem` exists, Gmail will **not** show your logo — DNS alone is not enough.

Submit to DigiCert for CMC:

```
ailt_api/app/assets/email/cheradip-avatar.png
```

(from Android `ic_launcher_foreground.png`)
