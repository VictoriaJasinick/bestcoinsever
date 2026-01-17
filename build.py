import re
import json
import math
import shutil
import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
DIST = ROOT / "dist"
STATIC = ROOT / "static"

def load_site():
    return yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))

def parse_frontmatter(text: str):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm_raw = text[3:end].strip()
            body = text[end+4:].lstrip("\n")
            fm = yaml.safe_load(fm_raw) or {}
            return fm, body
    return {}, text
def slugify_title(title: str) -> str:
    if not title:
        return ""
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]+", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s
def env():
    return Environment(
        loader=FileSystemLoader([str(ROOT / "templates"), str(ROOT / "includes")]),
        autoescape=select_autoescape(["html", "xml"]),
    )

def md():
    return Markdown(extensions=["extra", "sane_lists", "toc", "tables"])

def slug_to_out(slug: str) -> Path:
    if slug == "" or slug is None:
        return DIST / "index.html"
    if slug == "404":
        return DIST / "404.html"
    return DIST / slug / "index.html"

def canonical(base_url: str, slug: str) -> str:
    if slug == "" or slug is None:
        return base_url + "/"
    if slug == "404":
        return base_url + "/404.html"
    return base_url + f"/{slug}/"

def ensure_parent(p: Path):
    p.parent.mkdir(parents=True, exist_ok=True)

def write(p: Path, s: str):
    ensure_parent(p)
    p.write_text(s, encoding="utf-8")

def split_middle(html: str):
    parts = re.split(r"(</p>)", html, flags=re.IGNORECASE)
    ends = [i for i, x in enumerate(parts) if x.lower() == "</p>"]
    if len(ends) < 6:
        return html, ""
    cut_para = max(2, len(ends) // 3)
    cut_idx = ends[cut_para - 1]
    return "".join(parts[:cut_idx+1]), "".join(parts[cut_idx+1:])

def paginate(items, per_page):
    total = len(items)
    pages = max(1, math.ceil(total / per_page))
    for page in range(1, pages + 1):
        start = (page - 1) * per_page
        yield page, pages, items[start:start+per_page]

def related(posts, cur, limit=5):
    cur_tags = set([t.lower() for t in cur.get("tags", [])])
    cur_cat = cur.get("category", "")
    scored = []
    for p in posts:
        if p["slug"] == cur["slug"]:
            continue
        tags = set([t.lower() for t in p.get("tags", [])])
        score = len(cur_tags & tags)
        if p.get("category","") == cur_cat and cur_cat:
            score += 2
        if score > 0:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1].get("date","")), reverse=False)
    return [p for _, p in scored[:limit]]

def main():
    site = load_site()
    j = env()
    m = md()

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    # static copy
    if STATIC.exists():
        shutil.copytree(STATIC, DIST / "static", dirs_exist_ok=True)

    build_year = str(datetime.date.today().year)

    # categories
    category_map = {}
    for f in (CONTENT / "categories").glob("*.md"):
        fm, _ = parse_frontmatter(f.read_text(encoding="utf-8"))
        key = fm.get("slug")
        if key:
            category_map[key] = {
                "title": fm.get("title", key),
                "slug": fm.get("slug", key),
                "description": fm.get("description", ""),
            }

    # posts
    posts = []
    used_slugs = set()
    for f in sorted((CONTENT / "posts").glob("*.md")):
        fm, body = parse_frontmatter(f.read_text(encoding="utf-8"))
        html = m.convert(body); m.reset()
                slug = (fm.get("slug") or "").strip()
        if not slug:
            slug = slugify_title(fm.get("title", ""))
        if not slug:
            raise ValueError(f"Missing slug and cannot generate from title in file: {f.name}")

        if re.search(r"[^a-z0-9/-]", slug):
            raise ValueError(f"Invalid slug '{slug}' in file: {f.name} (allowed: a-z, 0-9, '-', '/')")

        if "//" in slug or slug.startswith("/") or slug.endswith("/"):
            raise ValueError(f"Invalid slug '{slug}' in file: {f.name} (no leading/trailing '/', no '//')")

        if slug in used_slugs:
            raise ValueError(f"Duplicate slug '{slug}' found (file: {f.name})")
        used_slugs.add(slug)
        cat_key = fm.get("category","")
        cat = category_map.get(cat_key)

        posts.append({
            "title": fm.get("title",""),
            "slug": slug,
            "url": f"/{slug}/" if slug else "/",
            "canonical_url": canonical(site["base_url"], slug),
            "description": fm.get("description", site["default_description"]),
            "meta_title": fm.get("meta_title", fm.get("title", site["site_name"])),
            "meta_description": fm.get("meta_description", fm.get("description", site["default_description"])),
            "date": fm.get("date",""),
            "category": cat_key,
            "category_title": cat["title"] if cat else "",
            "category_url": f"/category/{cat['slug']}/" if cat else "",
            "tags": fm.get("tags", []),
            "cover_image": fm.get("cover_image",""),
            "cover_alt": fm.get("cover_alt",""),
            "promo": bool(fm.get("promo", False)),
            "html": html,
        })

    posts.sort(key=lambda x: x.get("date",""), reverse=True)

    base_tpl = j.get_template("base.html")
    post_tpl = j.get_template("post.html")
    list_tpl = j.get_template("list.html")

    rendered_urls = []

    # render posts
    for p in posts:
        top, bottom = split_middle(p["html"])
        rel = related(posts, p, limit=5)

        page = dict(p)
        page["content_top"] = top
        page["content_bottom"] = bottom

        body = post_tpl.render(site=site, page=page, related=rel, build_year=build_year)
        full = base_tpl.render(site=site, page=page, body=body, related=rel, build_year=build_year)
        write(slug_to_out(p["slug"]), full)
        rendered_urls.append(p["url"])

    # render pages (home + policy + etc)
    for f in (CONTENT / "pages").glob("*.md"):
        fm, body_md = parse_frontmatter(f.read_text(encoding="utf-8"))
        slug = fm.get("slug","")
        html = m.convert(body_md); m.reset()

        page = {
            "title": fm.get("title", site["site_name"]),
            "slug": slug,
            "url": f"/{slug}/" if slug else "/",
            "canonical_url": canonical(site["base_url"], slug),
            "description": fm.get("description", site["default_description"]),
            "meta_title": fm.get("meta_title", fm.get("title", site["site_name"])),
            "meta_description": fm.get("meta_description", fm.get("description", site["default_description"])),
        }

        full = base_tpl.render(site=site, page=page, body=html, related=[], build_year=build_year)
        write(slug_to_out(slug), full)

        if slug != "404":
            rendered_urls.append(page["url"])

    # category listing pages with pagination
    per_page = int(site.get("posts_per_page", 12))
    for cat_key, cat in category_map.items():
        cat_posts = [p for p in posts if p.get("category") == cat_key]
        for page_num, total_pages, chunk in paginate(cat_posts, per_page):
            if page_num == 1:
                out = DIST / "category" / cat["slug"] / "index.html"
                url = f"/category/{cat['slug']}/"
            else:
                out = DIST / "category" / cat["slug"] / "page" / str(page_num) / "index.html"
                url = f"/category/{cat['slug']}/page/{page_num}/"

            pagination = {
                "page": page_num,
                "total_pages": total_pages,
                "prev_url": (f"/category/{cat['slug']}/" if page_num == 2 else f"/category/{cat['slug']}/page/{page_num-1}/") if page_num > 1 else None,
                "next_url": f"/category/{cat['slug']}/page/{page_num+1}/" if page_num < total_pages else None,
            }

            page = {
                "title": cat["title"],
                "description": cat["description"],
                "slug": f"category/{cat['slug']}",
                "url": url,
                "canonical_url": site["base_url"] + url,
                "meta_title": f"{cat['title']} | {site['site_name']}",
                "meta_description": cat["description"] or site["default_description"],
            }

            body = list_tpl.render(site=site, page=page, items=chunk, pagination=pagination)
            full = base_tpl.render(site=site, page=page, body=body, related=[], build_year=build_year)
            write(out, full)
            rendered_urls.append(url)

    # search index
    search_items = [{
        "title": p["title"],
        "description": p["description"],
        "url": p["url"],
        "tags": " ".join(p.get("tags", [])),
    } for p in posts]
    write(DIST / "static" / "search-index.json", json.dumps(search_items, ensure_ascii=False))

    # sitemap + robots
    today = datetime.date.today().isoformat()
    sitemap_urls = []
    for u in sorted(set(rendered_urls)):
        loc = site["base_url"] + u
        sitemap_urls.append(f"<url><loc>{loc}</loc><lastmod>{today}</lastmod></url>")

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(sitemap_urls) +
        "\n</urlset>\n"
    )
    write(DIST / "sitemap.xml", sitemap)

    robots = (
        "User-agent: *\n"
        "Disallow:\n"
        f"Sitemap: {site['base_url']}/sitemap.xml\n"
    )
    write(DIST / "robots.txt", robots)

if __name__ == "__main__":
    main()
