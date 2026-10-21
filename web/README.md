# What-If FC — web app

React + TypeScript frontend for browsing and replaying What-If FC match replays.

## Setup

```bash
cd web
npm install
```

Copy the environment file and set the API base URL:

```bash
cp .env.example .env
# edit VITE_API_BASE if your API runs on a different port
```

## Development

```bash
npm run dev
```

Opens at `http://localhost:5173` by default.

## Tests

```bash
npm test
```

## Production build

```bash
npm run build
```

Output goes to `dist/`.
