from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

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

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


# -------------------------
# Helpers
# -------------------------
def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
    s = (s or "").strip().lower()
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


def split_middle(html: str) -> Tuple[str, str]:
    """
    Splits HTML into two parts for inserting mid-article widgets/ads.
    If the article is short, returns (full, "").
    """
    parts = re.split(r"(</p>)", html, flags=re.IGNORECASE)
    ends = [i for i, x in enumerate(parts) if x.lower() == "</p>"]
    if len(ends) < 6:
        return html, ""
    cut_para = max(2, len(ends) // 3)
    cut_idx = ends[cut_para - 1]
    return "".join(parts[: cut_idx + 1]), "".join(parts[cut_idx + 1 :])


def paginate(items: List[Any], per_page: int) -> List[List[Any]]:
    if per_page <= 0:
        return [items]
    return [items[i : i + per_page] for i in range(0, len(items), per_page)] or [[]]


# -------------------------
# Site config (YAML -> dict)
# -------------------------
def load_site() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "site_name": "Best Coins Ever",
        "base_url": "https://bestcoinsever.com",
        "language": "en",
        "default_description": "Coin values, errors, and guides.",
        "posts_per_page": 12,
        "home_posts_count": 24,  # <= твой запрос
        "nav": [],               # меню вручную из site.yaml
    }

    if not SITE_YAML.exists():
        return defaults

    data = yaml.safe_load(read_text(SITE_YAML)) or {}
    if not isinstance(data, dict):
        data = {}

    site = {**defaults, **data}

    site["base_url"] = str(site.get("base_url") or defaults["base_url"]).rstrip("/")
    site["site_name"] = str(site.get("site_name") or site.get("name") or defaults["site_name"])
    site["language"] = str(site.get("language") or defaults["language"])
    site["default_description"] = str(
        site.get("default_description") or site.get("description") or defaults["default_description"]
    )

    # nav must be list of {label,url}
    nav = site.get("nav")
    if not isinstance(nav, list):
        nav = []
    cleaned_nav = []
    for item in nav:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        url = str(item.get("url") or "").strip()
        if label and url:
            cleaned_nav.append({"label": label, "url": url})
    site["nav"] = cleaned_nav

    # numeric fields
    try:
        site["posts_per_page"] = int(site.get("posts_per_page", defaults["posts_per_page"]))
    except Exception:
        site["posts_per_page"] = defaults["posts_per_page"]

    try:
        site["home_posts_count"] = int(site.get("home_posts_count", defaults["home_posts_count"]))
    except Exception:
        site["home_posts_count"] = defaults["home_posts_count"]

    return site


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


# -------------------------
# Related posts
# -------------------------
def compute_related(all_posts: List[Dict[str, Any]], cur: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    cur_tags = set([str(t).lower() for t in (cur.get("tags") or [])])
    cur_cat = str(cur.get("category") or "").strip()

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for p in all_posts:
        if p.get("slug") == cur.get("slug"):
            continue
        score = 0
        tags = set([str(t).lower() for t in (p.get("tags") or [])])
        score += len(cur_tags & tags)
        if cur_cat and str(p.get("category") or "") == cur_cat:
            score += 2
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("title") or "")))
    return [p for _, p in scored[:limit]]


# -------------------------
# Sitemap / robots
# -------------------------
def build_sitemap_xml(urls: List[str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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


# -------------------------
# Build
# -------------------------
def main() -> None:
    site = load_site()
    env = build_env()
    md = build_md()

    ensure_clean_dist()
    copy_static()

    categories = load_categories()

    sitemap_urls: List[str] = [canonical(site["base_url"], "/")]

    # ---------- Pages ----------
    if PAGES_DIR.exists():
        for f in sorted(PAGES_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))
            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()
            slug = normalize_slug(str(meta.get("slug") or f.stem))
            is_404 = (f.name == "404.md")

            html_body = md.reset().convert(body)
            top, bottom = split_middle(html_body)

            if is_404:
                rel = "/404.html"
                out_path = DIST_DIR / "404.html"
            else:
                rel = rel_url_from_slug(slug)
                out_path = output_path_for_slug(slug)
                sitemap_urls.append(canonical(site["base_url"], rel))

            page = {**meta, "title": title, "description": description}
            page["content_top"] = top
            page["content_bottom"] = bottom

            ctx = {
                "site": site,
                "categories": categories,
                "page": page,
                "title": title,
                "page_title": title,
                "description": description or site["default_description"],
                "meta_description": description or site["default_description"],
                "canonical": canonical(site["base_url"], rel),
                "canonical_url": canonical(site["base_url"], rel),
                "body": "",  # base uses block content; we render post/list templates
            }

            write_text(out_path, render(env, "post.html", ctx))

    # ---------- Posts ----------
    posts: List[Dict[str, Any]] = []
    used_slugs: set[str] = set()

    if POSTS_DIR.exists():
        for f in sorted(POSTS_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))

            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()

            slug = normalize_slug(str(meta.get("slug") or f.stem))
            if not slug:
                slug = normalize_slug(f.stem)

            if slug in used_slugs:
                raise ValueError(f"Duplicate slug '{slug}' found (post file: {f.name})")
            used_slugs.add(slug)

            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [t for t in re.split(r"[,\s]+", tags.strip()) if t]
            if not isinstance(tags, list):
                tags = [str(tags)]

            category = normalize_slug(str(meta.get("category") or ""))

            rel = rel_url_from_slug(slug)
            canon = canonical(site["base_url"], rel)

            html_body = md.reset().convert(body)
            top, bottom = split_middle(html_body)

            post_obj = {
                "title": title,
                "description": description,
                "slug": slug,
                "url": rel,
                "canonical": canon,
                "date": normalize_date(meta.get("date")),  # не отображается в шаблонах
                "category": category,
                "tags": tags,
            }
            posts.append(post_obj)

    # sort posts: date desc if present else title
    def sort_key(p: Dict[str, Any]) -> Tuple[str, str]:
        d = str(p.get("date") or "")
        return (d, str(p.get("title") or ""))

    posts.sort(key=sort_key, reverse=True)

    # render post pages (needs related)
    for p in posts:
        src_path = POSTS_DIR / f"{p['slug']}.md"
        # (мы не читаем повторно файл; content строим из meta/body выше? — проще заново прочитать по реальному файлу)
        # На практике slug может отличаться от filename, поэтому ищем исходный .md по slug через перебор.
        # Это безопасно и не ломает сборку.
        source_file: Optional[Path] = None
        for f in POSTS_DIR.glob("*.md"):
            m, _b = split_frontmatter(read_text(f))
            s = normalize_slug(str(m.get("slug") or f.stem))
            if s == p["slug"]:
                source_file = f
                meta, body = split_frontmatter(read_text(f))
                break
        if source_file is None:
            # fallback: пропускаем, если не нашли (не должно случаться)
            continue

        html_body = md.reset().convert(body)
        top, bottom = split_middle(html_body)

        related = compute_related(posts, p, limit=5)

        page = {**meta, "title": p["title"], "description": p["description"]}
        page["content_top"] = top
        page["content_bottom"] = bottom
        page["category_title"] = ""  # можно будет улучшить позже, если захочешь
        page["category_url"] = f"/category/{p['category']}/" if p.get("category") else ""

        ctx = {
            "site": site,
            "categories": categories,
            "page": page,
            "post": p,
            "related": related,
            "title": p["title"],
            "page_title": p["title"],
            "description": p["description"] or site["default_description"],
            "meta_description": p["description"] or site["default_description"],
            "canonical": p["canonical"],
            "canonical_url": p["canonical"],
            "body": "",
        }

        write_text(output_path_for_slug(p["slug"]), render(env, "post.html", ctx))
        sitemap_urls.append(p["canonical"])

    # ---------- Home (ONLY 24 posts) ----------
    home_count = int(site.get("home_posts_count", 24))
    home_posts = posts[:home_count]

    home_ctx = {
        "site": site,
        "categories": categories,
        "posts": home_posts,  # <= вот здесь ограничение
        "page": {
            "title": site["site_name"],
            "description": site.get("description") or site["default_description"],
            "slug": "",
        },
        "title": site["site_name"],
        "page_title": site["site_name"],
        "description": site.get("description") or site["default_description"],
        "meta_description": site.get("description") or site["default_description"],
        "canonical": canonical(site["base_url"], "/"),
        "canonical_url": canonical(site["base_url"], "/"),
        "pagination": None,
        "body": "",
    }
    write_text(DIST_DIR / "index.html", render(env, "list.html", home_ctx))

    # ---------- Category pages (pagination) ----------
    posts_by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for p in posts:
        posts_by_cat.setdefault(p.get("category") or "", []).append(p)

    per_page = int(site.get("posts_per_page", 12))

    for cat in categories:
        slug = cat["slug"]
        cat_posts = posts_by_cat.get(slug, [])
        chunks = paginate(cat_posts, per_page)

        total_pages = len(chunks) if chunks else 1
        for page_num, chunk in enumerate(chunks, start=1):
            if page_num == 1:
                rel = f"/category/{slug}/"
                out = DIST_DIR / "category" / slug / "index.html"
            else:
                rel = f"/category/{slug}/page/{page_num}/"
                out = DIST_DIR / "category" / slug / "page" / str(page_num) / "index.html"

            canon = canonical(site["base_url"], rel)

            pagination = {
                "page": page_num,
                "total_pages": total_pages,
                "prev_url": (f"/category/{slug}/" if page_num == 2 else f"/category/{slug}/page/{page_num-1}/")
                if page_num > 1
                else None,
                "next_url": f"/category/{slug}/page/{page_num+1}/" if page_num < total_pages else None,
            }

            ctx = {
                "site": site,
                "categories": categories,
                "posts": chunk,
                "category": cat,
                "page": {
                    "title": cat["title"],
                    "description": cat.get("description") or site["default_description"],
                    "slug": f"category/{slug}",
                },
                "title": f"{cat['title']} - {site['site_name']}",
                "page_title": f"{cat['title']} - {site['site_name']}",
                "description": cat.get("description") or site["default_description"],
                "meta_description": cat.get("description") or site["default_description"],
                "canonical": canon,
                "canonical_url": canon,
                "pagination": pagination,
                "body": "",
            }

            write_text(out, render(env, "list.html", ctx))
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
    unique_urls = sorted(set(sitemap_urls))
    write_text(DIST_DIR / "sitemap.xml", build_sitemap_xml(unique_urls))
    write_robots(site["base_url"])


if __name__ == "__main__":
    main()
