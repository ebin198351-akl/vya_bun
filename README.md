# vya_bun

Vya's Kitchen — handmade buns &amp; dumplings website (https://vya.co.nz).

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in GMAIL_APP_PASSWORD
python server.py       # http://localhost:8080
```

## Env vars

See `.env.example`. `GMAIL_APP_PASSWORD` is a 16-char Gmail App Password (see `GMAIL_SETUP.md`).
