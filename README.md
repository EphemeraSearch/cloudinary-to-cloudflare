# Cloudinary-to-Cloudflare

This repo contains a (highly-customized) script for importing into Cloudflare Images from Cloudinary.

Requirements:

- python
- `notify-send`
- A Cloudinary account
- A Cloudflare account with Cloudflare Images activated

### Setup

```
pip install -r requirements.txt
```

Set the following environment variables:

- `CLOUDFLARE_IMAGES_ACCOUNT_HASH`
- `CLOUDFLARE_IMAGES_ACCOUNT_ID`
- `CLOUDFLARE_IMAGES_API_TOKEN`
- `CLOUDINARY_URL`

### Usage

See `./migrate.py --help`
