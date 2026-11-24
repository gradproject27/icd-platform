"""Download UNSW-NB15 CSV files from the official public share (C2; never commit the files).

    python tools/c2/unsw_download.py --list
    python tools/c2/unsw_download.py UNSW-NB15_1.csv --out data/

The dataset page https://research.unsw.edu.au/projects/unsw-nb15-dataset links two public
SharePoint folders. A share link sets a session cookie; with it, SharePoint's REST API lists the
folder and serves the files. Standard library only. Prints names and sizes, never file content.
"""

import argparse
import http.cookiejar
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PAGE = "https://research.unsw.edu.au/projects/unsw-nb15-dataset"
UA = {"User-Agent": "Mozilla/5.0 (research data download)"}


def opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def share_links(op) -> list[str]:
    html = op.open(urllib.request.Request(PAGE, headers=UA), timeout=60).read().decode("utf-8")
    pattern = r"https://unsw-my\.sharepoint\.com/:f:/g/personal/[^\"<> ]+"
    return sorted(set(re.findall(pattern, html)))


def open_share(op, link: str) -> tuple[str, str]:
    """Follow a share link; returns (site URL, server-relative folder path)."""
    response = op.open(urllib.request.Request(link, headers=UA), timeout=60)
    final = response.geturl()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(final).query)
    folder = query.get("id", [None])[0]
    if folder is None:
        raise RuntimeError(f"no folder id in the redirect: {final.split('?')[0]}")
    site = final.split("/_layouts")[0] if "/_layouts" in final else final.split("/Documents")[0]
    return site, folder


def api(op, site: str, path: str) -> dict:
    request = urllib.request.Request(
        f"{site}/_api/web/{path}", headers={**UA, "Accept": "application/json;odata=nometadata"}
    )
    return json.loads(op.open(request, timeout=60).read())


def quote(path: str) -> str:
    return urllib.parse.quote(path.replace("'", "''"))


def walk(op, site: str, folder: str, depth: int = 0):
    """Yield (server-relative path, size) for every file under folder (depth 3 at most)."""
    for f in api(op, site, f"GetFolderByServerRelativeUrl('{quote(folder)}')/Files")["value"]:
        yield f["ServerRelativeUrl"], int(f["Length"])
    if depth < 3:
        sub = api(op, site, f"GetFolderByServerRelativeUrl('{quote(folder)}')/Folders")["value"]
        for d in sub:
            yield from walk(op, site, d["ServerRelativeUrl"], depth + 1)


def download(op, site: str, path: str, target: Path) -> int:
    url = f"{site}/_api/web/GetFileByServerRelativeUrl('{quote(path)}')/$value"
    size = 0
    with (
        op.open(urllib.request.Request(url, headers=UA), timeout=600) as src,
        target.open("wb") as dst,
    ):
        while chunk := src.read(1 << 20):
            dst.write(chunk)
            size += len(chunk)
    return size


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="file names to download, e.g. UNSW-NB15_1.csv")
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--list", action="store_true", help="list the files and sizes")
    args = parser.parse_args(argv)
    op = opener()
    files: dict[str, tuple[str, str, int]] = {}
    for link in share_links(op):
        try:
            site, folder = open_share(op, link)
            for path, size in walk(op, site, folder):
                files.setdefault(path.rsplit("/", 1)[-1], (site, path, size))
        except Exception as exc:  # report and try the other share
            print(f"share failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    if args.list:
        for _name, (_, path, size) in sorted(files.items()):
            print(f"{size:>12,}  {path}")
    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.names:
        if name not in files:
            print(f"not found: {name}", file=sys.stderr)
            return 1
        site, path, size = files[name]
        got = download(op, site, path, args.out / name)
        print(f"downloaded {name}: {got:,} bytes (listed {size:,})")
        if got != size:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
