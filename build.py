from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import random

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
    site_name: str = "Best Coins Ever"
    base_url: str = "https://bestcoinsever.com"
    language: str = "en"

    # Used by includes/head.html
    default_description: str = "Coin values, errors, and guides."
    twitter_handle: str = ""

    # Used by includes/header.html
    nav: List[Dict[str, str]] = field(default_factory=list)

    # Optional flags used by optional includes (safe if absent)
    use_cookie_banner: bool = True
    slots_enabled: bool = False
    adsense_enabled: bool = False
    promo_enabled: bool = False
    promo_links: List[Dict[str, str]] = field(default_factory=list)

    # Homepage behavior
    home_random_posts: int = 24


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def split_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        return {}, md_text
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        meta = {}
    body = m.group(2)
    return meta, body


def build_md() -> Markdown:
    return Markdown(extensions=["extra", "tables", "fenced_code", "sane_lists"])


def build_env() -> Environment:
    return Environment(
        loader=FileSystemLoader([str(TEMPLATES_DIR), str(INCLUDES_DIR)]),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render(env: Environment, template_name: str, ctx: Dict[str, Any]) -> str:
    return env.get_template(template_name).render(**ctx)


def load_site_config() -> SiteConfig:
    cfg = SiteConfig()
    if not SITE_YAML.exists():
        return cfg

    data = yaml.safe_load(read_text(SITE_YAML)) or {}
    if not isinstance(data, dict):
        return cfg

    cfg.site_name = str(data.get("site_name") or data.get("name") or cfg.site_name)
    cfg.base_url = str(data.get("base_url") or cfg.base_url).rstrip("/")
    cfg.language = str(data.get("language") or cfg.language)

    cfg.default_description = str(data.get("default_description") or data.get("description") or cfg.default_description)
    cfg.twitter_handle = str(data.get("twitter_handle") or cfg.twitter_handle)

    cfg.use_cookie_banner = bool(data.get("use_cookie_banner", cfg.use_cookie_banner))
    cfg.slots_enabled = bool(data.get("slots_enabled", cfg.slots_enabled))
    cfg.adsense_enabled = bool(data.get("adsense_enabled", cfg.adsense_enabled))
    cfg.promo_enabled = bool(data.get("promo_enabled", cfg.promo_enabled))

    # Homepage settings
    try:
        cfg.home_random_posts = int(data.get("home_random_posts", cfg.home_random_posts))
    except Exception:
        pass

    nav = data.get("nav") or []
    if isinstance(nav, list):
        cleaned_nav: List[Dict[str, str]] = []
        for item in nav:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if title and url:
                    cleaned_nav.append({"title": title, "url": url})
        cfg.nav = cleaned_nav

    promo_links = data.get("promo_links") or []
    if isinstance(promo_links, list):
        cleaned_promos: List[Dict[str, str]] = []
        for item in promo_links:
            if isinstance(item, dict):
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if title and url:
                    cleaned_promos.append({"title": title, "url": url})
        cfg.promo_links = cleaned_promos

    return cfg


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


def pick_home_posts(posts: List[Dict[str, Any]], desired: int) -> List[Dict[str, Any]]:
    """Pick a stable-yet-changing subset for the homepage.

    For SEO (and sanity), we avoid pure randomness on every build.
    This shuffles deterministically based on the current UTC date,
    so the homepage selection changes daily but is stable within a day.
    """
    if desired <= 0 or not posts:
        return []

    # Daily seed: YYYYMMDD + base salt from site name/length
    today = datetime.utcnow().strftime("%Y%m%d")
    seed = int(today)
    rng = random.Random(seed)

    shuffled = posts[:]  # copy
    rng.shuffle(shuffled)
    return shuffled[: min(desired, len(shuffled))]


def main() -> None:
    site = load_site_config()
    env = build_env()
    md = build_md()

    ensure_clean_dist()
    copy_static()

    categories = load_categories()
    categories_by_slug = {c["slug"]: c for c in categories}

    sitemap_urls: List[str] = [canonical(site.base_url, "/")]

    build_year = datetime.utcnow().year

    used_slugs: Dict[str, str] = {}

    # ---------- Pages ----------
    if PAGES_DIR.exists():
        for f in sorted(PAGES_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))
            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()

            is_404 = (f.name == "404.md")
            slug = normalize_slug(str(meta.get("slug") or f.stem))

            html_body = md.reset().convert(body)

            if is_404:
                rel = "/404.html"
                out_path = DIST_DIR / "404.html"
            else:
                if slug in used_slugs:
                    raise ValueError(f"Duplicate slug '{slug}' found (page file: {f.name}, already used by: {used_slugs[slug]})")
                used_slugs[slug] = f.name

                rel = rel_url_from_slug(slug)
                out_path = output_path_for_slug(slug)
                sitemap_urls.append(canonical(site.base_url, rel))

            page_cat_slug = normalize_slug(str(meta.get("category") or ""))
            cat = categories_by_slug.get(page_cat_slug)
            page_category_title = cat["title"] if cat else ""
            page_category_url = cat["url"] if cat else ""

            page = {
                **meta,
                "title": title,
                "description": description,
                "date": normalize_date(meta.get("date")),
                "slug": slug,
                "url": rel,
                "category": page_cat_slug,
                "category_title": page_category_title,
                "category_url": page_category_url,
                "content_top": html_body,
                "content_bottom": "",
            }

            ctx = {
                "site": site.__dict__,
                "categories": categories,
                "page": page,
                "title": title,
                "page_title": title,
                "description": description or site.default_description,
                "meta_description": description or site.default_description,
                "canonical": canonical(site.base_url, rel),
                "canonical_url": canonical(site.base_url, rel),
                "body": html_body,
                "build_year": build_year,
                "related": [],
            }

            template_name = "post.html" if (TEMPLATES_DIR / "post.html").exists() else "base.html"
            write_text(out_path, render(env, template_name, ctx))

    # ---------- Posts (collect first) ----------
    posts_raw: List[Dict[str, Any]] = []
    if POSTS_DIR.exists():
        for f in sorted(POSTS_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))
            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()

            slug = normalize_slug(str(meta.get("slug") or f.stem))
            if slug in used_slugs:
                raise ValueError(f"Duplicate slug '{slug}' found (post file: {f.name}, already used by: {used_slugs[slug]})")
            used_slugs[slug] = f.name

            post_date = normalize_date(meta.get("date"))
            category_slug = normalize_slug(str(meta.get("category") or ""))

            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [t for t in re.split(r"[,\s]+", tags.strip()) if t]
            if not isinstance(tags, list):
                tags = [str(tags)]

            rel = rel_url_from_slug(slug)
            canon = canonical(site.base_url, rel)

            html_body = md.reset().convert(body)

            cat = categories_by_slug.get(category_slug)
            category_title = cat["title"] if cat else category_slug
            category_url = cat["url"] if cat else (f"/category/{category_slug}/" if category_slug else "")

            post_obj = {
                "title": title,
                "description": description,
                "slug": slug,
                "url": rel,
                "canonical": canon,
                "date": post_date,
                "category": category_slug,
                "category_title": category_title,
                "category_url": category_url,
                "tags": tags,
            }

            page = {
                **meta,
                "title": title,
                "description": description,
                "date": post_date,
                "slug": slug,
                "url": rel,
                "category": category_slug,
                "category_title": category_title,
                "category_url": category_url,
                "content_top": html_body,
                "content_bottom": "",
            }

            posts_raw.append(
                {
                    "post": post_obj,
                    "page": page,
                    "html": html_body,
                }
            )

            sitemap_urls.append(canon)

    # Sort posts.
    # If you don't use dates in frontmatter, we keep a stable A->Z order by title.
    has_any_date = any((p["post"].get("date") or "").strip() for p in posts_raw)
    if has_any_date:
        # Newest first (string ISO dates sort correctly).
        posts_raw.sort(key=lambda x: (x["post"].get("date", ""), x["post"].get("title", "")), reverse=True)
    else:
        posts_raw.sort(key=lambda x: (x["post"].get("title", ""), x["post"].get("slug", "")))
    posts = [p["post"] for p in posts_raw]

    # Related posts helper
    def related_for(post: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        same_cat = [p for p in posts if p.get("slug") != post.get("slug") and p.get("category") and p.get("category") == post.get("category")]
        if len(same_cat) >= limit:
            return same_cat[:limit]
        fallback = [p for p in posts if p.get("slug") != post.get("slug") and p not in same_cat]
        return (same_cat + fallback)[:limit]

    # ---------- Render posts ----------
    for item in posts_raw:
        post_obj = item["post"]
        page = item["page"]
        slug = post_obj["slug"]
        rel = post_obj["url"]
        canon = post_obj["canonical"]

        ctx = {
            "site": site.__dict__,
            "categories": categories,
            "page": page,
            "post": post_obj,
            "title": post_obj["title"],
            "page_title": post_obj["title"],
            "description": post_obj["description"] or site.default_description,
            "meta_description": post_obj["description"] or site.default_description,
            "canonical": canon,
            "canonical_url": canon,
            "body": item["html"],
            "build_year": build_year,
            "related": related_for(post_obj, limit=5),
        }

        write_text(output_path_for_slug(slug), render(env, "post.html", ctx))

    # ---------- Home ----------
    home_template = "list.html" if (TEMPLATES_DIR / "list.html").exists() else "base.html"
    # SEO note: we keep the homepage lightweight and link to a rotating subset of posts.
    # Discovery for the rest is handled by category pages + sitemap.xml.
    home_posts = pick_home_posts(posts, desired=max(0, int(site.home_random_posts or 0)))
    home_ctx = {
        "site": site.__dict__,
        "categories": categories,
        "posts": home_posts,
        "page": {
            "title": site.site_name,
            "description": site.default_description,
            "slug": "",
            "date": "",
        },
        "title": site.site_name,
        "page_title": site.site_name,
        "description": site.default_description,
        "meta_description": site.default_description,
        "canonical": canonical(site.base_url, "/"),
        "canonical_url": canonical(site.base_url, "/"),
        "body": "",
        "build_year": build_year,
    }
    write_text(DIST_DIR / "index.html", render(env, home_template, home_ctx))

    # ---------- Category pages ----------
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
                "page": {
                    "title": cat["title"],
                    "description": cat.get("description") or site.default_description,
                    "slug": f"category/{slug}",
                    "date": "",
                },
                "title": f"{cat['title']} - {site.site_name}",
                "page_title": f"{cat['title']} - {site.site_name}",
                "description": cat.get("description") or site.default_description,
                "meta_description": cat.get("description") or site.default_description,
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
                "body": "",
                "build_year": build_year,
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
