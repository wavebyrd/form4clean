# Form4Clean dashboard

The React frontend for `form4clean dashboard`. It is built into `src/form4clean/api/static/`,
which is committed so that `pip install form4clean` works without Node.

```bash
npm install
npm run dev        # http://localhost:5173, proxies /api to form4clean on port 8765
npm run typecheck
npm run lint
npm test
npm run build      # writes ../src/form4clean/api/static
```

Run `form4clean dashboard --no-browser` in another terminal so the dev server has an API to talk
to. After changing the frontend, run `npm run build` and commit the updated static files.

See [docs/dashboard.md](../docs/dashboard.md) for how the dashboard works.
