---
title: Guitar Chord Coach
emoji: 🎸
colorFrom: yellow
colorTo: red
sdk: docker
pinned: false
app_port: 7860
---

# Guitar Chord Coach (public demo)

Upload a song → detect chords → show them above the lyrics.

**Free host:** this Space runs on Hugging Face’s free CPU tier.

### Notes
- First request can be slow (models download/cache).
- “Isolate guitar” needs a lot of memory — it may fail on the free tier; chord + lyrics still work without it.
- Max clip length is 4 minutes.
