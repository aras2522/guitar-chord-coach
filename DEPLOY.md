# Free public deploy

Hugging Face **Docker Spaces are paid now**. On that Create Space screen:

## What to do on the Hugging Face page

1. **Do not** choose **Static** — that can’t run this Python app  
2. **Do not** subscribe to PRO just for this (unless you want to)  
3. **Leave / cancel** that page  

Use **Render** instead (still has a free web service).

---

## Free path: Render.com

### Limits of free Render
- 512 MB RAM → we deploy a **lite** build (`Dockerfile.lite`)
- Works: upload, chord detection, lyrics lookup (enter title/artist), demo
- Disabled: Isolate guitar, Whisper transcription
- Sleeps after ~15 min idle (first open can be slow)

### Steps

1. Put the project on **GitHub** (free):
   ```bash
   cd ~/guitar-chord-coach
   git init
   git add .
   git commit -m "Guitar Chord Coach ready for Render"
   # create a new empty repo on github.com, then:
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/guitar-chord-coach.git
   git push -u origin main
   ```

2. Sign up at [https://render.com](https://render.com) (free)

3. **Dashboard → New → Web Service**

4. Connect your GitHub repo `guitar-chord-coach`

5. Settings:
   - **Language / Runtime:** Docker  
   - **Dockerfile Path:** `Dockerfile.lite`  
   - **Instance type:** Free  
   - **Health Check Path:** `/api/health`

6. Create Web Service and wait for the build

7. Open the public URL Render gives you (like `https://guitar-chord-coach.onrender.com`)

### After it’s live
- Enter **song title + artist** (e.g. Free Bird / Lynyrd Skynyrd) before upload  
- Keep editing locally → `git push` → Render redeploys  

---

## If you want full Isolate guitar later
That needs more RAM (paid Render, AWS/Azure VM, or Hugging Face PRO Docker Space).
