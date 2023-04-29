#!/usr/bin/env python3

import click
import cloudinary
import cloudinary.uploader
import json
import os
import requests
import sys
import tabulate
from IPython import embed
from collections import OrderedDict

cf_account_id = os.environ["CLOUDFLARE_IMAGES_ACCOUNT_ID"]
cf_token = os.environ["CLOUDFLARE_IMAGES_API_TOKEN"]
cf_url = f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}/images/v1"
env = os.environ["DJANGO_ENV"]
folder = f"{env}/ephemera"


def cf_headers():
    return {
        "Authorization": f"Bearer {cf_token}",
    }


def cloudflare_get(path):
    resp = requests.get(path, headers=cf_headers())
    ret = None
    try:
        ret = resp.json()
    except:
        ret = resp.content.decode()
        click.secho(ret, fg="yellow")
    return ret


def cloudflare_delete_by_id(image_id):
    path = f"{cf_url}/{image_id}"
    click.secho(f"Calling DELETE: {path}", fg='yellow')
    resp = requests.delete(path, headers=cf_headers())
    ret = None
    try:
        ret = resp.json()
    except:
        ret = resp.content.decode()
        click.secho(ret, fg="yellow")
    return ret

def cf_list(per_page=2, page=2):
    url = f"{cf_url}?per_page={per_page}&page={page}"
    return cloudflare_get(url)


def cf_post(resource, i, replace=False):
    image_id = f"{folder}/{resource['etag']}"
    _public_id = click.style("public_id", bold=True)
    _asset_id = click.style("asset_id", bold=True)
    _etag = click.style("etag", bold=True)
    _image_id = click.style(image_id, bold=True)
    _ephemeron = click.style(image_id, bold=True)

    cl_url = resource["url"]
    cl_metadata = resource.get("context", {})
    ephemeron = cl_metadata.get("ephemeron", "unknown")

    click.secho(
        (
            f"POSTING: ({i}) {_public_id} = {resource['public_id']} "
            f"{_asset_id} = {resource['asset_id']} "
            f"{_etag} = {resource['etag']} -> {_image_id}  {_ephemeron}={ephemeron}"
        ),
        fg="magenta",
    )

    cl_metadata.update(
        {
            "env": env,
            "cloudinary": {
                "asset_id": resource["asset_id"],
                "created_at": resource["created_at"],
                "etag": resource["etag"],
                "filename": resource["filename"],
                "folder": resource["folder"],
                "height": resource["height"],
                "public_id": resource["public_id"],
                "secure_url": resource["secure_url"],
                "uploaded_at": resource["uploaded_at"],
                "url": resource["url"],
                "version": resource["version"],
                "width": resource["width"],
            },
        }
    )

    data = {
        "requireSignedURLs": "false",
        "metadata": json.dumps(cl_metadata),
        "url": cl_url,
        "id": image_id,
    }
    headers = cf_headers()
    resp = requests.post(cf_url, headers=headers, files=data)
    status = resp.status_code

    if status in [409, 200]:
        # add cloudflare tag to cloudinary resource
        cloudinary.uploader.add_context(f"cloudflare=true", [resource["public_id"]])

    if resp.status_code == 409:
        click.secho(f"Already exists: {resource['asset_id']}", fg="yellow")
        if not replace:
            return resp
        del data["url"]
        del data["id"]
        # This time we send json instead of form data.
        data["requireSignedURLs"] = False
        data["metadata"] = cl_metadata
        update_url = f"{cf_url}/{image_id}"
        updated = requests.patch(update_url, headers=headers, json=data)
        if updated.status_code == 200:
            print("updated")
        else:
            print("failed to update")
            embed()
        #  print(updated.content.decode())
        # requests.delete(update_url, headers=headers)
    elif resp.status_code == 200:
        click.secho(f"Uploaded: {resource['asset_id']}", fg="green")
    else:
        click.secho(f"Something went wrong: {resource['asset_id']}", fg="red")
        embed()

    return resp


def cl_image_by_etag(etag):
    result = (
        cloudinary.Search()
        .expression(
            f"resource_type:image AND folder={folder} AND etag={etag} AND !context:cloudflare"
        )
        .with_field("context")
        .execute()
    )


def cl_list(max_results=1, next_cursor=None):
    if not next_cursor:
        click.secho(f"importing from folder {folder}", fg="magenta")
    result = (
        cloudinary.Search()
        .expression(f"resource_type:image AND folder={folder} AND !context:cloudflare")
        .with_field("context")
        .max_results(max_results)
        .sort_by("public_id", "desc")
        .next_cursor(next_cursor)
        .execute()
    )
    return result


def cl_import(next_cursor=None, max_results=5):
    i = 0
    while True:
        result = cl_list(next_cursor=next_cursor, max_results=max_results)
        total_count = result["total_count"]
        next_cursor = result.get("next_cursor")
        resources = result["resources"]
        click.secho(f"Doing {len(resources)} Cloudinary resources...")
        click.secho(
            f"Completed: {i} of {total_count}, next_cursor = {next_cursor}", fg="cyan"
        )
        for resource in resources:
            resp = cf_post(resource, i, replace=False)
            if resp.status_code not in [200, 409]:
                embed(header=f"bad status code={resp.status_code}")
            i += 1
        if not next_cursor:
            break

    return result


CONTEXT_SETTINGS = dict(
    help_option_names=["-h", "--help"], token_normalize_func=lambda x: x.lower()
)


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    pass


@cli.command()
@click.argument("etag")
def by_etag(etag):
    """Find an image by its etag."""
    cl_image_by_etag(etag)


@cli.command(name="import")
@click.option("-l", "--limit", default=3)
@click.option("-n", "--next-cursor", default=None)
def import_images(next_cursor, limit):
    """Import images from Cloudinary to Cloudflare."""
    if next_cursor:
        click.secho(f"Starting after next cursor: {next_cursor}", fg="red")
    cl_import(next_cursor=next_cursor, max_results=limit)


@cli.command(name="delete")
@click.argument("cloudflare-id")
def delete_from_cloudflare(cloudflare_id):
    """Delete Cloudflare image."""
    if not click.confirm(f"Sure to delete image {cloudflare_id}?", default=True):
        print("Aborting.")
        sys.exit()

    result = cloudflare_delete_by_id(cloudflare_id)
    print(result)


@cli.command()
@click.option("-pp", "--per-page", default=10)  # Must be <= 10
@click.option("-p", "--page", default=1)
def list_cloudflare_images(per_page, page):
    """List images Cloudflare."""
    click.secho(f"Starting at page {page} with {per_page} results per page.", fg="cyan")
    while True:
        click.secho(f"Page: {page}")
        result = cf_list(per_page=per_page, page=page)
        if 'result' not in result:
            click.secho("Something went wrong", fg='red')
            print(result)
            sys.exit()

        images = result['result']['images']
        items = []
        for image in images:
            meta = image['meta']
            cloudinary = image.get('meta', {}).get('cloudinary', {})
            etag = cloudinary.get('etag') or meta.get("etag")
            if cloudinary.get("etag"):
                etag = click.style(etag, fg='green')
            else:
                etag = click.style(etag, fg='magenta')
            if cloudinary.get("etag") and meta.get("etag"):
                etag = click.style(etag, fg='red')

            _id = image.get('id')
            env = meta.get('env', 'WAT')
            if env == "WAT":
                click.secho(f"'env' key missing from meta: {meta}", fg='yellow')
            if not _id.startswith(env):
                _id = click.style(_id, fg='red')

            items.append(OrderedDict({
                "id": _id,
                "uploaded": image.get('uploaded'),
                "source": image.get('source'),
                "etag": etag,
                "user": meta.get('user'),
                "source": meta.get('source'),
                "eph": meta.get('ephemeron'),
                "cloudinary_asset_id": cloudinary.get('asset_id'),
                "width": cloudinary.get('width'),
                "height": cloudinary.get('height'),
            }))
        print(tabulate.tabulate(items, headers='keys'))
        if not click.confirm("Do you want more?", default=True):
            embed()
            break
        if len(images) < per_page:
            click.secho("That's all, we think.")
            break
        page += 1

if __name__ == "__main__":
    cli(obj={})
