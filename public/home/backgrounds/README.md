# Homepage backgrounds

Drop `.jpg`, `.jpeg`, `.png`, `.webp`, or `.svg` files in this folder. Hugo discovers them automatically for the homepage; no quote-script or template edits are needed. Use landscape images around 1800 px wide, and keep the subject and highlights subdued so the quote stays primary.

Optionally add one or more time-period suffixes before the extension to give an image preferred pools: `--dawn`, `--morning`, `--day`, `--dusk`, or `--night` (for example, `quiet-water--dawn--dusk.webp`). Untagged images remain available at every time. The matching pool is favored about 75% of the time when it has images, while the rest of the library remains in the draw.

The local clock periods are dawn (05:00–07:59), morning (08:00–10:59), day (11:00–15:59), dusk (16:00–18:59), and night (19:00–04:59). The current images have their time-period tags in `data/home_background_periods.yaml`. For new images, add period suffixes directly to the filename to avoid editing the tag map.
