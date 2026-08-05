const fileInput = document.getElementById("fileInput");
const demoBtn = document.getElementById("demoBtn");
const isolateToggle = document.getElementById("isolateToggle");
const lyricsInput = document.getElementById("lyricsInput");
const titleInput = document.getElementById("titleInput");
const artistInput = document.getElementById("artistInput");
const statusEl = document.getElementById("status");
const workspace = document.getElementById("workspace");
const player = document.getElementById("player");
const currentChord = document.getElementById("currentChord");
const songMeta = document.getElementById("songMeta");
const chordBoard = document.getElementById("chordBoard");
const songChart = document.getElementById("songChart");
const tip = document.getElementById("tip");

let segments = [];
let chartLines = [];
let activeChordName = null;
let activeLineIndex = -1;

function setStatus(text, { error = false, busy = false } = {}) {
  statusEl.hidden = !text;
  statusEl.textContent = text;
  statusEl.classList.toggle("error", error);
  statusEl.classList.toggle("busy", busy);
}

function diagramSvg(shape = [-1, -1, -1, -1, -1, -1], label = "—") {
  const frets = 5;
  const strings = 6;
  const left = 28;
  const top = 40;
  const width = 140;
  const height = 150;
  const dx = width / (strings - 1);
  const dy = height / frets;

  let grid = "";
  for (let s = 0; s < strings; s++) {
    const x = left + s * dx;
    grid += `<line x1="${x}" y1="${top}" x2="${x}" y2="${top + height}" stroke="currentColor" stroke-opacity="0.55" stroke-width="${s === 0 || s === 5 ? 2.2 : 1.2}"/>`;
  }
  for (let f = 0; f <= frets; f++) {
    const y = top + f * dy;
    grid += `<line x1="${left}" y1="${y}" x2="${left + width}" y2="${y}" stroke="currentColor" stroke-opacity="${f === 0 ? 0.95 : 0.35}" stroke-width="${f === 0 ? 4 : 1}"/>`;
  }

  let marks = "";
  shape.forEach((fret, i) => {
    const x = left + i * dx;
    if (fret < 0) {
      marks += `<text x="${x}" y="${top - 14}" text-anchor="middle" fill="currentColor" opacity="0.65" font-size="14">×</text>`;
    } else if (fret === 0) {
      marks += `<circle cx="${x}" cy="${top - 12}" r="5" fill="none" stroke="#c45c1a" stroke-width="2"/>`;
    } else if (fret <= frets) {
      const y = top + (fret - 0.5) * dy;
      marks += `<circle cx="${x}" cy="${y}" r="8" fill="#c45c1a"/>`;
    } else {
      marks += `<text x="${x}" y="${top - 14}" text-anchor="middle" fill="#c45c1a" font-size="11">${fret}</text>`;
    }
  });

  return `
    <svg viewBox="0 0 200 230" role="img" aria-label="${label} chord diagram">
      <text x="100" y="22" text-anchor="middle" fill="currentColor" font-family="Fraunces, serif" font-size="20">${label}</text>
      ${grid}
      ${marks}
    </svg>
  `;
}

function firstStartForChord(name) {
  const seg = segments.find((s) => s.chord === name);
  return seg ? seg.start : 0;
}

function renderChordBoard(chords) {
  chordBoard.innerHTML = "";
  chords.forEach((item) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "chord-card";
    card.dataset.chord = item.chord;
    card.innerHTML = diagramSvg(item.shape, item.chord);
    card.addEventListener("click", () => {
      player.currentTime = firstStartForChord(item.chord) + 0.01;
      player.play();
      paintAt(player.currentTime);
    });
    chordBoard.appendChild(card);
  });
}

function highlightChord(name) {
  [...chordBoard.children].forEach((card) => {
    card.classList.toggle("active", card.dataset.chord === name);
  });
}

function renderSongChart(chart) {
  chartLines = chart?.lines || [];
  songChart.innerHTML = "";
  songChart.classList.toggle("no-lyrics", chart && chart.has_lyrics === false);

  chartLines.forEach((line, index) => {
    if (line.type === "break") {
      const gap = document.createElement("div");
      gap.className = "chart-break";
      songChart.appendChild(gap);
      return;
    }
    if (line.type === "section") {
      const h = document.createElement("h3");
      h.className = "chart-section";
      h.textContent = line.label || "SECTION";
      songChart.appendChild(h);
      return;
    }

    const row = document.createElement("button");
    row.type = "button";
    row.className = "chart-line";
    row.dataset.index = String(index);
    if (line.start != null) row.dataset.start = String(line.start);

    const cellsRow = document.createElement("div");
    cellsRow.className = "chart-cells";

    (line.cells || []).forEach((cell) => {
      const col = document.createElement("span");
      col.className = "chart-cell";

      const chordCell = document.createElement("span");
      chordCell.className = "chart-chord";
      chordCell.textContent = cell.chord || "\u00A0";
      if (cell.chord) chordCell.dataset.chord = cell.chord;

      const wordCell = document.createElement("span");
      wordCell.className = "chart-word";
      wordCell.textContent = cell.text || "";

      col.appendChild(chordCell);
      col.appendChild(wordCell);
      cellsRow.appendChild(col);
    });

    row.appendChild(cellsRow);
    row.addEventListener("click", () => {
      if (line.start != null) {
        player.currentTime = line.start + 0.01;
        player.play();
        paintAt(player.currentTime);
      }
    });
    songChart.appendChild(row);
  });
}

function atTime(list, time) {
  return list.find((s) => time >= s.start && time < s.end) || null;
}

function lineIndexAt(time) {
  let found = -1;
  chartLines.forEach((line, index) => {
    if (line.type !== "lyric" || line.start == null || line.end == null) return;
    if (time >= line.start && time < line.end) found = index;
  });
  return found;
}

function paintChord(seg) {
  if (!seg) {
    currentChord.textContent = "—";
    highlightChord(null);
    activeChordName = null;
    return;
  }
  if (activeChordName !== seg.chord) {
    activeChordName = seg.chord;
    currentChord.textContent = seg.chord;
    currentChord.classList.remove("pulse");
    void currentChord.offsetWidth;
    currentChord.classList.add("pulse");
    highlightChord(seg.chord);
  }
  songChart.querySelectorAll(".chart-chord").forEach((el) => {
    el.classList.toggle("active", el.dataset.chord === seg.chord);
  });
}

function paintLine(time) {
  const idx = lineIndexAt(time);
  if (idx === activeLineIndex) return;
  activeLineIndex = idx;
  songChart.querySelectorAll(".chart-line").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.index) === idx);
  });
  const active = songChart.querySelector(".chart-line.active");
  if (active) {
    active.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function paintAt(time) {
  paintChord(atTime(segments, time) || segments[segments.length - 1] || null);
  paintLine(time);
}

function renderResult(data) {
  segments = data.segments || [];
  activeChordName = null;
  activeLineIndex = -1;
  workspace.hidden = false;
  player.src = data.audio_url;
  const mode = data.chart?.has_lyrics
    ? data.chart?.source === "lrclib"
      ? "catalog lyrics"
      : data.chart?.source === "transcription"
        ? "auto lyrics"
        : "lyrics chart"
    : "chord sheet";
  const songLabel = [data.song_artist, data.song_title].filter(Boolean).join(" — ");
  songMeta.textContent = `${songLabel || data.filename} · ${Number(data.duration).toFixed(1)}s · ${mode}`;
  tip.textContent = data.tip || "";

  const boardChords =
    data.unique_chords && data.unique_chords.length
      ? data.unique_chords
      : [...new Map(segments.map((s) => [s.chord, { chord: s.chord, shape: s.shape }])).values()];
  renderChordBoard(boardChords);
  renderSongChart(data.chart || { lines: [], has_lyrics: false });
  paintAt(0);
}

async function analyze(url, { formData } = {}) {
  const isolating = Boolean(formData && isolateToggle?.checked);
  const hasPaste = Boolean(lyricsInput?.value?.trim());
  let msg = "Building song chart…";
  if (isolating && !hasPaste) msg = "Isolating guitar + lyrics agent working…";
  else if (isolating) msg = "Isolating guitar and building chart…";
  else if (!hasPaste && formData) msg = "Lyrics agent looking up lyrics + detecting chords…";
  setStatus(msg, { busy: true });
  try {
    const res = await fetch(url, formData ? { method: "POST", body: formData } : undefined);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? data.detail[0]?.msg : data.detail;
      throw new Error(detail || "Analysis failed");
    }
    setStatus("Ready — follow the chords above the lyrics.");
    renderResult(data);
  } catch (err) {
    setStatus(err.message || "Something went wrong", { error: true });
  }
}

demoBtn.addEventListener("click", () => analyze("/api/demo"));

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  fd.append("isolate", isolateToggle.checked ? "true" : "false");
  fd.append("lyrics", lyricsInput.value || "");
  fd.append("title", titleInput?.value || "");
  fd.append("artist", artistInput?.value || "");
  analyze("/api/analyze", { formData: fd });
});

player.addEventListener("timeupdate", () => {
  paintAt(player.currentTime);
});

// Hide heavy features on free/lite deploys.
fetch("/api/health")
  .then((r) => r.json())
  .then((data) => {
    if (data.lite_mode || data.isolate_available === false) {
      const row = document.getElementById("isolateRow");
      if (row) row.hidden = true;
      if (isolateToggle) isolateToggle.checked = false;
    }
  })
  .catch(() => {});
