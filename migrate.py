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
    click.secho(f"Calling DELETE: {path}", fg="yellow")
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
    _ephemeron = click.style("ephemeron", bold=True)

    cl_url = resource["url"]
    cl_metadata = resource.get("context", {})
    cl_metadata.pop("cloudflare", None)
    ephemeron = cl_metadata.get("ephemeron", "unknown")

    cl_metadata.update(
        {
            "env": env,
            "cloudinary": {
                "asset_id": resource["asset_id"],
                "bytes": resource["bytes"],
                "created_at": resource["created_at"],
                "etag": resource["etag"],
                "filename": resource["filename"],
                "folder": resource["folder"],
                "format": resource["format"],
                "height": resource["height"],
                "public_id": resource["public_id"],
                "secure_url": resource["secure_url"],
                "uploaded_at": resource["uploaded_at"],
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
    click.secho(
        (
            f"POSTING: ({i}) {_public_id} = {resource['public_id']} "
            f"{_asset_id} = {resource['asset_id']} "
            f"{_etag} = {resource['etag']} -> {_image_id}  {_ephemeron}={ephemeron}"
        ),
        fg="magenta",
        nl=False,
    )

    resp = requests.post(cf_url, headers=headers, files=data)
    status = resp.status_code
    click.secho("✅ ", fg="yellow")

    if status in [409, 200]:
        # add cloudflare tag to cloudinary resource
        click.secho(f"Adding 'cloudflare=true' to Cloudinary resource... ", nl=False)
        cl_resp = cloudinary.uploader.add_context(
            f"cloudflare=true", [resource["public_id"]]
        )
        click.secho(f"done", fg="green")

    if status == 409:
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
        patch_status = updated.status_code
        if patch_status == 200:
            print("updated")
        else:
            msg = f"failed to update, got {patch_status} response"
            click.secho(msg, fg="red")
            os.system('notify-send "you are being prompted"')
            embed(header=msg)
        #  print(updated.content.decode())
        # requests.delete(update_url, headers=headers)
    elif status == 200:
        click.secho(f"Uploaded/tagged: {resource['asset_id']}", fg="green")
    elif status in [500]:
        click.secho(f"Something went wrong: {resource['asset_id']}", fg="red")
        click.secho(resp.content.decode())
    else:
        click.secho(
            f"Something unexpected went wrong: {resource['asset_id']}", fg="red"
        )
        click.secho(resp.content.decode())
        os.system('notify-send "you are being prompted"')
        embed()
        raise RuntimeError("Something unexpected went wrong")

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


def cl_list(max_results=1, next_cursor=None, replace=False):
    if not next_cursor:
        click.secho(f"importing from folder {folder}", fg="magenta")
    extra = "AND context:cloudflare" if replace else "AND !context:cloudflare"
    result = (
        cloudinary.Search()
        .expression(f"resource_type:image AND folder={folder} {extra}")
        .with_field("context")
        .max_results(max_results)
        .sort_by("public_id", "desc")
        .next_cursor(next_cursor)
        .execute()
    )
    return result


def cl_import(next_cursor=None, max_results=5, replace=False):
    i = 0
    while True:
        result = cl_list(
            next_cursor=next_cursor, max_results=max_results, replace=replace
        )
        total_count = result["total_count"]
        next_cursor = result.get("next_cursor")
        resources = result["resources"]
        click.secho(f"Doing {len(resources)} Cloudinary resources...")
        click.secho(
            f"Completed: {i} of {total_count}, next_cursor = {next_cursor}", fg="cyan"
        )
        for resource in resources:
            resp = cf_post(resource, i, replace=replace)
            if resp.status_code in [200, 409]:
                pass
            elif resp.status_code in [500, 524]:
                # It's fine if we skip a few, they'll be reimported again since they
                # won't have the cloudflare=true tag.
                continue
            else:
                os.system('notify-send "you are being prompted"')
                embed(header=f"bad status code={resp.status_code}")
            i += 1
        if not next_cursor:
            break
        if False and not click.confirm("More?", default=True):
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
@click.option("-r", "--replace", is_flag=True, default=False)
def import_images(next_cursor, limit, replace):
    """Import images from Cloudinary to Cloudflare."""
    if next_cursor:
        click.secho(
            f"Starting after next cursor: {next_cursor} replace={replace}", fg="red"
        )
    cl_import(next_cursor=next_cursor, max_results=limit, replace=replace)


@cli.command(name="delete")
@click.argument("cloudflare-id")
def delete_from_cloudflare(cloudflare_id):
    """Delete Cloudflare image."""
    os.system('notify-send "you are being prompted"')
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
        if "result" not in result:
            click.secho("Something went wrong, 'result' not in result", fg="red")
            print(result)
            sys.exit()

        images = result["result"]["images"]
        items = []
        for image in images:
            meta = image.get("meta", {})
            cloudinary = meta.get("cloudinary", {"wat": "how"})
            if "cloudinary" in meta:
                del meta["cloudinary"]  # facilitate inspection

            cloudinary_etag = cloudinary.get("etag")
            cloudflare_etag = meta.get("etag")
            etag = click.style(
                cloudinary_etag or cloudflare_etag,
                fg="cyan" if cloudinary_etag else "yellow",
            )

            if cloudinary.get("etag") and meta.get("etag"):
                etag = click.style(etag, fg="red")

            _id = image.get("id")
            env = meta.get("env", "WAT")
            if env == "WAT":
                click.secho(f"'env' key missing from meta: {meta}", fg="yellow")
            if not _id.startswith(env):
                _id = click.style(_id, fg="red")

            items.append(
                OrderedDict(
                    {
                        "id": _id,
                        "etag": etag,
                        "cloudinary_asset_id": cloudinary.get("asset_id"),
                        "cl_filename": cloudinary.get("filename"),
                        "cl_created_at": cloudinary.get("created_at", "")[0:16],
                        "uploaded": image.get("uploaded", "")[0:16],
                        "user": meta.get("user"),
                        "eph": meta.get("ephemeron"),
                        "col.": meta.get("collections"),
                        "source": meta.get("source"),
                        "dimensions": f'{cloudinary.get("width")} x {cloudinary.get("height")}',
                        "bytes": cloudinary.get("bytes"),
                        #  "secure_url": cloudinary.get("secure_url"),
                    }
                )
            )
        print(tabulate.tabulate(items, headers="keys"))
        if not click.confirm("Do you want more?", default=True):
            embed()
            break
        if len(images) < per_page:
            click.secho("That's all, we think.")
            break
        page += 1


if __name__ == "__main__":
    cli(obj={})
