# V3.1 — Business domain consolidation

The following implementations now live under
`src/agentforge/domains/{websites,media,growth}/`. Existing flat imports are
aliases to the **same** Python module object.

- **Websites**: builder, assets, quality, revision, browser_validation,
  design_kit and local image_studio.
- **Media**: assets, quality, render and workflow.
- **Growth**: store, reports and bundle.

No website/media output directories or campaign SQLite paths moved.
The new canonical files that compute ROOT use
`agentforge.paths.REPOSITORY_ROOT` rather than file depth.

`agentforge.architecture.BUSINESS_DOMAIN_IMPORTS` is the canonical migration
map, verified by `tests/test_business_domains_v31.py`.

Legacy Python invocations such as `python -m agentforge.product_builder`,
`python -m agentforge.media_workflow_v15`,
`python -m agentforge.web_assets` and
`python -m agentforge.browser_validation` continue to invoke their new
canonical main entrypoints.

No AI-generation, publish, model provider, financial action or data deletion
is performed by this refactor; behaviour is covered by the existing
product/media/growth tests. Remaining specialty modules will migrate only
when their dependency/root behavior has dedicated tests.
