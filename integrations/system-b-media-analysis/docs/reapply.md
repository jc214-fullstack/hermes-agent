# Reapply / Restore Notes

Copy `integrations/hermes-hooks/media-analysis-intake` to `/home/imagi/.hermes/hooks/media-analysis-intake`.
Copy `integrations/hermes-hooks/media-analysis-z-backend` to `/home/imagi/.hermes/hooks/media-analysis-z-backend`.
Copy `live-media-analysis-lib` to `/home/imagi/media-analysis/lib`.

Do not restart the Hermes gateway unless Mike explicitly approves. Hook code changes on disk require a gateway restart before they affect new live link drops.

After reapply, run focused validation from the Hermes checkout and the old staging repo if still present:

```bash
cd /home/imagi/projects/instagram-reel-analyzer && pytest -q
cd /home/imagi/.hermes/hermes-agent && python -m pytest tests/gateway/test_media_analysis_hook.py -q -o 'addopts='
```
