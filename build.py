from __future__ import annotations

import json
import random
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
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


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


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


def load_site() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "site_name": "Best Coins Ever",
        "base_url": "https://bestcoinsever.com",
        "description": "Coin values, errors, and guides.",
        "language": "en",
        "nav": [],
        "home_posts_count": 24,
        "related_posts_count": 5,
    }

    site: Dict[str, Any] = dict(defaults)

    if SITE_YAML.exists():
        data = yaml.safe_load(read_text(SITE_YAML)) or {}
        if isinstance(data, dict):
            site.update(data)

    site["base_url"] = str(site.get("base_url") or defaults["base_url"]).rstrip("/")
    site["site_name"] = str(site.get("site_name") or site.get("name") or defaults["site_name"])
    site["description"] = str(site.get("description") or defaults["description"])
    site["language"] = str(site.get("language") or defaults["language"])

    # nav must be list of {title,url} (we also keep {label,url} for backward compatibility)
    cleaned_nav = []
    raw_nav = site.get("nav") or []
    if isinstance(raw_nav, list):
        for item in raw_nav:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("label") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url:
                continue
            cleaned_nav.append({"title": title, "label": title, "url": url})
    site["nav"] = cleaned_nav

    try:
        site["home_posts_count"] = int(site.get("home_posts_count", defaults["home_posts_count"]))
    except Exception:
        site["home_posts_count"] = defaults["home_posts_count"]

    try:
        site["related_posts_count"] = int(site.get("related_posts_count", defaults["related_posts_count"]))
    except Exception:
        site["related_posts_count"] = defaults["related_posts_count"]

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


def compute_related_posts(
    current: Dict[str, Any],
    all_posts: List[Dict[str, Any]],
    categories_map: Dict[str, Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    cur_slug = current.get("slug", "")
    cur_cat = current.get("category", "")
    cur_tags = set([str(t).lower() for t in (current.get("tags") or [])])

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for p in all_posts:
        if p.get("slug") == cur_slug:
            continue
        score = 0
        if cur_cat and p.get("category") == cur_cat:
            score += 3
        p_tags = set([str(t).lower() for t in (p.get("tags") or [])])
        score += len(cur_tags.intersection(p_tags))
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored][: max(0, int(limit))]

    for p in top:
        cat_slug = p.get("category") or ""
        if cat_slug and cat_slug in categories_map:
            p["category_title"] = categories_map[cat_slug]["title"]
            p["category_url"] = categories_map[cat_slug]["url"]
    return top


def ensure_unique_output_path(slug: str) -> str:
    slug = normalize_slug(slug)
    out = output_path_for_slug(slug)
    if not out.exists():
        return slug

    n = 2
    while True:
        candidate = f"{slug}-{n}" if slug else f"{n}"
        out2 = output_path_for_slug(candidate)
        if not out2.exists():
            return candidate
        n += 1


def main() -> None:
    site = load_site()
    env = build_env()
    md = build_md()

    ensure_clean_dist()
    copy_static()

    categories = load_categories()
    categories_map = {c["slug"]: c for c in categories}

    sitemap_urls: List[str] = [canonical(site["base_url"], "/")]

    # ---------- Posts ----------
    posts: List[Dict[str, Any]] = []
    if POSTS_DIR.exists():
        for f in sorted(POSTS_DIR.glob("*.md")):
            meta, body = split_frontmatter(read_text(f))
            title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
            description = str(meta.get("description") or "").strip()

            raw_slug = str(meta.get("slug") or f.stem)
            slug = normalize_slug(raw_slug)

            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [t for t in re.split(r"[,\s]+", tags.strip()) if t]
            if not isinstance(tags, list):
                tags = [str(tags)]

            category = normalize_slug(str(meta.get("category") or ""))

            rel = rel_url_from_slug(slug)
            canon = canonical(site["base_url"], rel)

            html_body = md.reset().convert(body)

            post_obj = {
                "title": title,
                "description": description,
                "slug": slug,
                "url": rel,
                "canonical": canon,
                "category": category,
                "tags": tags,
            }

            if category and category in categories_map:
                post_obj["category_title"] = categories_map[category]["title"]
                post_obj["category_url"] = categories_map[category]["url"]

            posts.append(post_obj)

    # shuffle posts deterministically per build
    random.shuffle(posts)

    # ---------- Render Posts ----------
    for p in posts:
        slug = ensure_unique_output_path(p["slug"])
        p["slug"] = slug
        p["url"] = rel_url_from_slug(slug)
        p["canonical"] = canonical(site["base_url"], p["url"])

    # rebuild map after possible slug adjustments
    posts_by_slug = {p["slug"]: p for p in posts}

    for f in sorted(POSTS_DIR.glob("*.md")) if POSTS_DIR.exists() else []:
        meta, body = split_frontmatter(read_text(f))
        title = str(meta.get("title") or f.stem.replace("-", " ").title()).strip()
        description = str(meta.get("description") or "").strip()

        raw_slug = str(meta.get("slug") or f.stem)
        norm_slug = normalize_slug(raw_slug)

        # find matching post after slug adjustment
        post_obj = None
        for p in posts:
            if p.get("title") == title and normalize_slug(p.get("slug")) == normalize_slug(norm_slug):
                post_obj = p
                break
        if post_obj is None:
            # fallback by original normalized slug
            post_obj = posts_by_slug.get(norm_slug)

        if post_obj is None:
            continue

        html_body = md.reset().convert(body)

        related_limit = int(site.get("related_posts_count", 5))
        related = compute_related_posts(post_obj, posts, categories_map, related_limit)

        page_ctx = {
            "title": title,
            "description": description or site["description"],
            "slug": post_obj["slug"],
            "category_title": post_obj.get("category_title"),
            "category_url": post_obj.get("category_url"),
            "content_top": html_body,
            "content_bottom": "",
        }

        ctx = {
            "site": site,
            "categories": categories,
            "page": page_ctx,
            "post": post_obj,
            "related_posts": related,
            "title": title,
            "page_title": title,
            "description": description or site["description"],
            "meta_description": description or site["description"],
            "canonical": post_obj["canonical"],
            "canonical_url": post_obj["canonical"],
        }

        body_html = render(env, "post.html", ctx)
        full_html = render(env, "base.html", {**ctx, "body": body_html})
        write_text(output_path_for_slug(post_obj["slug"]), full_html)
        sitemap_urls.append(post_obj["canonical"])

    # ---------- Home (ONLY 24 posts) ----------
    home_count = int(site.get("home_posts_count", 24))
    home_posts = posts[:home_count]

    home_ctx = {
        "site": site,
        "categories": categories,
        "posts": home_posts,
        "page": {
            "title": site["site_name"],
            "description": site["description"],
            "slug": "",
        },
        "title": site["site_name"],
        "page_title": site["site_name"],
        "description": site["description"],
        "meta_description": site["description"],
        "canonical": canonical(site["base_url"], "/"),
        "canonical_url": canonical(site["base_url"], "/"),
    }

    body_html = render(env, "list.html", home_ctx)
    full_html = render(env, "base.html", {**home_ctx, "body": body_html})
    write_text(DIST_DIR / "index.html", full_html)

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

            canon = canonical(site["base_url"], rel)

            ctx = {
                "site": site,
                "categories": categories,
                "posts": chunk,
                "category": cat,
                "current_category": cat,
                "page": {
                    "title": cat["title"],
                    "description": cat.get("description") or site["description"],
                    "slug": f"category/{slug}",
                },
                "title": f"{cat['title']} - {site['site_name']}",
                "page_title": f"{cat['title']} - {site['site_name']}",
                "description": cat.get("description") or site["description"],
                "meta_description": cat.get("description") or site["description"],
                "canonical": canon,
                "canonical_url": canon,
                "pagination": {
                    "page": i,
                    "total_pages": len(chunks),
                    "prev_url": (f"/category/{slug}/" if i == 2 else f"/category/{slug}/page/{i-1}/") if i > 1 else "",
                    "next_url": f"/category/{slug}/page/{i+1}/" if i < len(chunks) else "",
                },
            }

            body_html = render(env, "list.html", ctx)
            full_html = render(env, "base.html", {**ctx, "body": body_html})
            write_text(out, full_html)
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
    write_robots(site["base_url"])


if __name__ == "__main__":
    main()

{% extends "base.html" %}

{% block content %}
<section class="list">
  <header class="list-header">
    <h1>{{ page.title }}</h1>
    {% if page.description %}<p class="muted">{{ page.description }}</p>{% endif %}
  </header>

  <div class="cards">
    {% for post in posts %}
      <article class="card">
        <h2 class="card-title"><a href="{{ post.url }}">{{ post.title }}</a></h2>
        {% if post.description %}<p class="card-desc">{{ post.description }}</p>{% endif %}
        {% if post.category %}
          <p class="card-meta muted">{{ post.category }}</p>
        {% endif %}
      </article>
    {% endfor %}
  </div>

  {% if pagination %}
    <nav class="pagination" aria-label="Pagination">
      {% if pagination.prev_url %}<a class="btn" href="{{ pagination.prev_url }}">← Prev</a>{% endif %}
      <span class="muted">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
      {% if pagination.next_url %}<a class="btn" href="{{ pagination.next_url }}">Next →</a>{% endif %}
    </nav>
  {% endif %}
</section>
{% endblock %}
