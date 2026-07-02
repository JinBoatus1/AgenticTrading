# Landing page (Replit export)

Marketing landing page shown at `/` before the main dashboard at `/app`.

## Structure

- `src/` — React + Vite + Tailwind source (from Replit)
- Built static output is copied into `../frontend/`:
  - `index.html` — landing entry
  - `assets/` — Vite bundle (JS/CSS/images)
  - `favicon.svg`

## Rebuild (optional)

The repo ships pre-built assets. To rebuild after editing `src/`:

```bash
cd dashboard/landing
npm install   # or pnpm install from monorepo root if applicable
BASE_PATH=/ PORT=5173 npm run build
cp -r dist/public/assets ../frontend/assets
cp dist/public/index.html ../frontend/index.html
# Re-apply CTA bridge script in index.html if overwritten (Open Playground → /app)
```

CTA buttons in source link to `/app` and the Discord invite.
