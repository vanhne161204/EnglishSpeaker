# EnglishTalker — Mobile App (React Native + Expo)

Cross-platform (iOS + Android) client written in TypeScript.

```
src/
  api/          API client + per-resource calls (topics, ...)
  components/    reusable UI (TopicCard, ...)
  config/        environment resolution (API base URL)
  navigation/    React Navigation stack
  screens/       screen components (HomeScreen, ...)
  theme/         colors, spacing, radius tokens
  types/         shared TypeScript types
App.tsx          app root (providers + navigator)
```

## Prerequisites

- Node.js 20+
- Expo Go on your phone, or an iOS Simulator / Android Emulator

## Run

```bash
cd frontend
npm install
npm start          # then press i (iOS), a (Android), or scan the QR in Expo Go
```

> Start the backend first (see `../backend/README.md`). The app auto-targets
> `localhost:8000` (iOS sim) or `10.0.2.2:8000` (Android emulator). For a physical
> device, set `expo.extra.apiBaseUrl` in `app.json` to your machine's LAN IP.

## Quality

```bash
npm run typecheck
npm run lint
```

## Note on real-time features

The demo lists topics over REST. Live audio practice will use `react-native-webrtc`
plus a streaming STT provider (see `../docs/06_Architecture.md`). `react-native-webrtc`
requires a custom dev build (not Expo Go) — added when the conversation feature lands.
