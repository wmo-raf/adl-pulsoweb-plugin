# Contributing

## Documentation

`docs/guide.md` is the operator guide for this plugin. It is the single place
configuration is documented — the README deliberately stays short — and it is
aggregated into the central ADL documentation site.

**A pull request that touches the connection or station-link models (adding,
removing or renaming a field, changing a default or a validation rule), the
variable-mapping model, or any admin surface this plugin adds (a page, a
button, a form, a widget) must update `docs/guide.md` in the same PR.** If the
change is visible on screen, also update `docs/screenshots.yml` and regenerate
the images with the capture harness in the `adl` repo:

```bash
# from a checkout of wmo-raf/adl, with Docker running
scripts/capture-plugin-docs.sh ../adl-plugins/adl-pulsoweb-plugin
```

Images are code: never hand-edit a PNG in `docs/images/`; change the manifest
entry and regenerate. Keep images free of text (only numbered badges), since
the docs are translated.

Messages the plugin shows to operators (source-check results, admin banners)
are listed verbatim-shaped in the guide's feedback catalogue — add a row when
you add or change one.

## Development

See the README for the dev stack. Lint with `make lint` and format with
`make format` inside `plugins/adl_pulsoweb_plugin/`.

## Releases

Tag releases bare (`0.3.0`, never `v0.3.0`): `plugins.toml` entries pin the tag
verbatim. Use `gh release create 0.3.0`.
