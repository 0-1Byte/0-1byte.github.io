# Homepage backgrounds

Drop `.jpg`, `.jpeg`, `.png`, `.webp`, or `.svg` files in this folder. Hugo discovers them automatically for the homepage; no quote-script or template edits are needed. Use landscape images around 1800 px wide, and keep the subject and highlights subdued so the quote stays primary.

For raster photos, run `python -m pip install Pillow` once, then
`python tools/optimize_home_backgrounds.py`. This generates a mobile portrait crop
(up to 840 × 1400 px) and a desktop image (up to 1920 × 1280 px) in WebP format in
`static/home/backgrounds-optimized/`.
The GitHub Pages workflow runs this step before Hugo. The original files remain
available as a fallback and retain their existing URLs; the homepage selects a
single size appropriate to the viewport.

Existing time-period tags in `data/home_background_periods.yaml` are retained as
catalog metadata only. The homepage draws uniformly from the full background
library, excluding the two most recently shown images; it does not weight a
time-of-day subset.
