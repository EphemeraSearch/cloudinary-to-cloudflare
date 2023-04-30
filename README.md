# Cloudinary-to-Cloudflare

This repo contains a (highly-customized) script for importing into Cloudflare Images from Cloudinary.

Requirements:

- python
- `notify-send`

### Setup

```
pip install -r requirements.txt
```

Set the following environment variables:

- `CLOUDFLARE_IMAGES_ACCOUNT_HASH`
- `CLOUDFLARE_IMAGES_ACCOUNT_ID`
- `CLOUDFLARE_IMAGES_API_TOKEN`

### Usage

See `./migrate.py --help`
