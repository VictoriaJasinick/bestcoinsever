from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown


ROOT = Path(__file__).parent.resolve()

CONTENT_DIR = ROOT / "content"
POSTS_DIR = CONTENT_DIR / "posts"
PAGES_DIR = CONTENT_DIR / "pages"
CATEGORIES_DIR = CONTENT_DIR / "categories"

TEMPLATES_DIR = ROOT / "templates"
INCLUDES_DIR = ROOT / "includes"
STATIC_DIR = ROOT / "static"

SITE_YAML = ROOT / "site.yaml"

DIST_DIR = ROOT / "dist"
DIST_STATIC_DIR = DIST_DIR / "static"


@dataclass
class SiteConfig:
    site_name: str
    base_url: str
    description: str
    language: str = "en"


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_site_config() -> SiteConfig:
    if not SITE_YAML.exists():
        return SiteConfig(
            site_name="Best Coins Ever",
            base_url="https://bestcoinsever.com",
            description="Coin values, errors, and guides.",
            language="en",
        )
    data = yaml.safe_load(read_text(SITE_YAML)) or {}
    return SiteConfig(
        site_name=str(data.get("site_name") or data.get("name") or "Best Coins Ever"),
        base_url=str(data.get("base_url") or "https://bestcoinsever.com").rstrip("/"),
        description=str(data.get("description") or "Coin values, errors, and guides."),
        language=str(data.get("language") or "en"),
    )


def split_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        return {}, md_text
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    body = m.group(2)
    return meta, body


def normalize_date(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    return str(value)


def slugify_segment(s: str) -> str:
    s = s.strip().lower()
    s = s.replace("_", "-")
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def normalize_slug(raw: str) -> str:
    raw = (raw or "").strip().strip("/")
    if not raw:
        return ""
    parts = [p for p in raw.split("/") if p.strip()]
    parts = [slugify_segment(p) for p in parts]
    parts = [p for p in parts if p]
    return "/".join(parts)


def rel_url_from_slug(slug: str) -> str:
    slug = normalize_slug(slug)
    if not slug:
        return "/"
    return f"/{slug}/"


def output_path_for_slug(slug: str) -> Path:
    slug = normalize_slug(slug)
    if not slug:
        return DIST_DIR / "index.html"
    return DIST_DIR / slug / "index.html"


def canonical(base_url: str, rel: str) -> str:
    rel = "/" + rel.lstrip("/")
    return base_url.rstrip("/") + rel


def ensure_clean_dist() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    DIST_STATIC_DIR.mkdir(parents=True, exist_ok=True)


def copy_static() -> None:
    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, DIST_STATIC_DIR, dirs_exist_ok=True)


def build_md() -> Markdown:
    return Markdown(extensions=["extra", "tables", "fenced_code", "sane_lists"])


def build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader([str(TEMPLATES_DIR), str(INCLUDES_DIR)]),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render(env: Environment, template_name: str, ctx: Dict[str, Any]) -> str:
    return env.get_template(template_name).render(**ctx)


def load_categories() -> List[Dict[str, Any]]:
    cats: List[Dict[str, Any]] = []
    if not CATEGORIES_DIR.exists():
        return cats

    for f in sorted(CATEGORIES_DIR.glob("*.md")):
        meta, _ = split_frontmatter(read_text(f))
        title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
        description = str(meta.get("description") or "").strip()
        slug = normalize_slug(str(meta.get("slug") or f.stem))
        cats.append(
            {
                "title": title,
                "description": description,
                "slug": slug,
                "url": f"/category/{slug}/",
            }
        )
    return cats


def build_sitemap_xml(urls: List[str]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    items = []
    for u in urls:
        items.append(
            "  <url>\n"
            f"    <loc>{u}</loc>\n"
            f"    <lastmod>{now}</lastmod>\n"
            "  </url>"
        )
    body = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def write_robots(base_url: str) -> None:
    txt = "User-agent: *\nAllow: /\n\n" + f"Sitemap: {base_url.rstrip('/')}/sitemap.xml\n"
    write_text(DIST_DIR / "robots.txt", txt)


def paginate(items: List[Any], per_page: int) -> List[List[Any]]:
    if per_page <= 0:
        return [items]
    return [items[i : i + per_page] for i in range(0, len(items), per_page)] or [[]]


def main() -> None:
    site = load_site_config()
    env = build_env()
    md = build_md()

    ensure_clean_dist()
    copy_static()

    categories = load_categories()
    sitemap_urls: List[str] = [canonical(site.base_url, "/")]

    # ---------- Pages ----------
    if PAGES_DIR.exists():
        for f in sorted(PAGES_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))
            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()

            slug = normalize_slug(str(meta.get("slug") or f.stem))
            is_404 = (f.name == "404.md")

            html_body = md.reset().convert(body)

            if is_404:
                rel = "/404.html"
                out_path = DIST_DIR / "404.html"
            else:
                rel = rel_url_from_slug(slug)
                out_path = output_path_for_slug(slug)
                sitemap_urls.append(canonical(site.base_url, rel))

            ctx = {
                "site": site.__dict__,
                "categories": categories,
                "page": {**meta, "date": normalize_date(meta.get("date"))},
                "title": title,
                "page_title": title,
                "description": description or site.description,
                "meta_description": description or site.description,
                "canonical": canonical(site.base_url, rel),
                "canonical_url": canonical(site.base_url, rel),
                "content": html_body,
                "content_html": html_body,
                "body": html_body,
            }

            template_name = "post.html" if (TEMPLATES_DIR / "post.html").exists() else "base.html"
            write_text(out_path, render(env, template_name, ctx))

    # ---------- Posts ----------
    posts: List[Dict[str, Any]] = []
    if POSTS_DIR.exists():
        for f in sorted(POSTS_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))
            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()

            slug = normalize_slug(str(meta.get("slug") or f.stem))
            post_date = normalize_date(meta.get("date"))

            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [t for t in re.split(r"[,\s]+", tags.strip()) if t]
            if not isinstance(tags, list):
                tags = [str(tags)]

            category = normalize_slug(str(meta.get("category") or ""))

            rel = rel_url_from_slug(slug)
            canon = canonical(site.base_url, rel)

            html_body = md.reset().convert(body)

            post_obj = {
                "title": title,
                "description": description,
                "slug": slug,
                "url": rel,
                "canonical": canon,
                "date": post_date,
                "category": category,
                "tags": tags,
            }
            posts.append(post_obj)

            ctx = {
                "site": site.__dict__,
                "categories": categories,
                "page": {**meta, "date": post_date},
                "post": post_obj,
                "title": title,
                "page_title": title,
                "description": description or site.description,
                "meta_description": description or site.description,
                "canonical": canon,
                "canonical_url": canon,
                "content": html_body,
                "content_html": html_body,
                "body": html_body,
            }

            write_text(output_path_for_slug(slug), render(env, "post.html", ctx))
            sitemap_urls.append(canon)

    # сортировка постов по дате-строке (без падений)
    posts.sort(key=lambda x: (x.get("date", ""), x.get("title", "")), reverse=True)

    # ---------- Home ----------
    home_template = "list.html" if (TEMPLATES_DIR / "list.html").exists() else "base.html"
    home_ctx = {
        "site": site.__dict__,
        "categories": categories,
        "posts": posts,
        "title": site.site_name,
        "page_title": site.site_name,
        "description": site.description,
        "meta_description": site.description,
        "canonical": canonical(site.base_url, "/"),
        "canonical_url": canonical(site.base_url, "/"),
        "content": "",
        "content_html": "",
        "body": "",
    }
    write_text(DIST_DIR / "index.html", render(env, home_template, home_ctx))

    # ---------- Category pages (optional, if you want) ----------
    posts_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for p in posts:
        posts_by_cat.setdefault(p.get("category") or "", []).append(p)

    per_page = 10
    for cat in categories:
        slug = cat["slug"]
        cat_posts = posts_by_cat.get(slug, [])
        chunks = paginate(cat_posts, per_page)

        for i, chunk in enumerate(chunks, start=1):
            if i == 1:
                rel = f"/category/{slug}/"
                out = DIST_DIR / "category" / slug / "index.html"
            else:
                rel = f"/category/{slug}/page/{i}/"
                out = DIST_DIR / "category" / slug / "page" / str(i) / "index.html"

            canon = canonical(site.base_url, rel)
            ctx = {
                "site": site.__dict__,
                "categories": categories,
                "posts": chunk,
                "category": cat,
                "current_category": cat,
                "title": f"{cat['title']} - {site.site_name}",
                "page_title": f"{cat['title']} - {site.site_name}",
                "description": cat.get("description") or site.description,
                "meta_description": cat.get("description") or site.description,
                "canonical": canon,
                "canonical_url": canon,
                "pagination": {
                    "page": i,
                    "pages": len(chunks),
                    "has_prev": i > 1,
                    "has_next": i < len(chunks),
                    "prev_url": f"/category/{slug}/" if i == 2 else f"/category/{slug}/page/{i-1}/",
                    "next_url": f"/category/{slug}/page/{i+1}/",
                },
                "content": "",
                "content_html": "",
                "body": "",
            }
            write_text(out, render(env, home_template, ctx))
            sitemap_urls.append(canon)

    # ---------- Search index ----------
    search_index = [
        {
            "title": p.get("title", ""),
            "description": p.get("description", ""),
            "url": p.get("url", ""),
            "tags": " ".join([str(t) for t in (p.get("tags") or [])]),
        }
        for p in posts
    ]
    write_text(DIST_STATIC_DIR / "search-index.json", json.dumps(search_index, ensure_ascii=False))

    # ---------- Sitemap + robots ----------
    write_text(DIST_DIR / "sitemap.xml", build_sitemap_xml(sitemap_urls))
    write_robots(site.base_url)


if __name__ == "__main__":
    main()
