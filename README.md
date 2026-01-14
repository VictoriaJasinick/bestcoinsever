# BestCoinsEver.com

Static site build:
- Markdown content in `content/`
- Templates in `templates/`, includes in `includes/`
- Output HTML in `dist/`

Build:
python3 -m pip install -r requirements.txt
python3 build.py

Deploy:
Use any CI/CD (Cloudflare Pages / Netlify / GitHub Actions) to run the build and publish `dist/`.
