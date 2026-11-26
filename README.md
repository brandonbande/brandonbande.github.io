# brandonbande.co.zw

The professional website of Brandon T. Bande: Systems Thinker, AI Builder, Business Analyst.

All copy and facts live in `content/` as JSON data objects. `scripts/build.py` (Python 3
standard library only) renders them with the templates in `templates/` and the assets in
`static/` into `dist/`, which GitHub Actions deploys to GitHub Pages.

```sh
python3 scripts/build.py                        # draft build into dist/ (DRAFT banner, noindex)
python3 scripts/build.py --release              # release build: fails on unapproved content
python3 scripts/images.py                       # portrait variants + social card (needs Pillow)
python3 -m http.server --directory dist 8000    # preview at http://localhost:8000
```
