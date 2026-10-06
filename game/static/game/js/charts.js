/* Time Bomb Stats — graphiques (Chart.js).
 *
 * Les données arrivent via des balises <script type="application/json"> générées
 * par le filtre Django `json_script`. Les couleurs sont lues dans les variables
 * CSS : les graphiques se redessinent quand le thème change.
 */
(() => {
  "use strict";

  if (typeof Chart === "undefined") return;

  const readJSON = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const isDark = () => {
    const forced = document.documentElement.dataset.theme;
    return forced ? forced === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  };
  const fmtPct = (v) => (v == null ? "—" : `${Math.round(v)} %`);
  const fmtDay = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "2-digit" });

  // Palette catégorielle validée (bleu et rouge exclus : réservés aux camps).
  const SERIES = {
    light: ["#eb6834", "#1baf7a", "#4a3aa7", "#e87ba4", "#eda100"],
    dark: ["#d95926", "#199e70", "#9085e9", "#d55181", "#c98500"],
  };
  const MAX_HIGHLIGHT = SERIES.light.length;

  const theme = () => ({
    text: cssVar("--text"),
    text2: cssVar("--text-2"),
    muted: cssVar("--muted"),
    grid: cssVar("--grid"),
    surface: cssVar("--surface"),
    surface3: cssVar("--surface-3"),
    kind: cssVar("--kind"),
    villain: cssVar("--villain"),
    accent: cssVar("--accent"),
    series: isDark() ? SERIES.dark : SERIES.light,
  });

  const applyDefaults = (t) => {
    Chart.defaults.font.family = cssVar("--font") || "system-ui, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = t.muted;
    Chart.defaults.borderColor = t.grid;
    Chart.defaults.maintainAspectRatio = false;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    Chart.defaults.animation = firstRender || reduced ? false : { duration: 350 };
    Object.assign(Chart.defaults.plugins.tooltip, {
      backgroundColor: t.text,
      titleColor: t.surface,
      bodyColor: t.surface,
      padding: 10,
      cornerRadius: 10,
      displayColors: true,
      boxPadding: 4,
      usePointStyle: true,
    });
    Chart.defaults.plugins.legend.display = false;
  };

  const axis = (t, extra = {}) => ({
    grid: { color: t.grid, drawTicks: false },
    border: { display: false },
    ticks: { color: t.muted, padding: 8 },
    ...extra,
  });

  /* Étiquettes directes : nom du joueur au bout de sa courbe / à côté de sa bulle.
   * Les étiquettes qui se chevaucheraient sont décalées (courbes) ou masquées
   * (bulles, le nom reste disponible au survol). */
  const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const directLabels = {
    id: "directLabels",
    afterDatasetsDraw(chart, _args, opts) {
      if (!opts || !opts.enabled) return;
      const { ctx, chartArea: area } = chart;
      ctx.save();
      ctx.font = `600 12px ${Chart.defaults.font.family}`;
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      const lineHeight = 14;

      if (opts.mode === "bubble") {
        const placed = [];
        const items = [];
        chart.data.datasets.forEach((ds, i) => {
          chart.getDatasetMeta(i).data.forEach((pt, j) => items.push({ pt, raw: ds.data[j] }));
        });
        // les bulles elles-mêmes sont des obstacles (carré inscrit, un peu réduit)
        items.forEach(({ pt }) => {
          const r = pt.options.radius * 0.8;
          placed.push({ x: pt.x - r, y: pt.y - r, w: 2 * r, h: 2 * r });
        });
        // les plus grosses bulles d'abord : ce sont elles qu'on veut nommer
        items.sort((a, b) => b.raw.r - a.raw.r);
        items.forEach(({ pt, raw }) => {
          const w = ctx.measureText(raw.name).width;
          const r = pt.options.radius;
          const candidates = [
            { x: pt.x + r + 4, y: pt.y - lineHeight / 2 },
            { x: pt.x - r - 4 - w, y: pt.y - lineHeight / 2 },
            { x: pt.x - w / 2, y: pt.y - r - lineHeight - 2 },
            { x: pt.x - w / 2, y: pt.y + r + 2 },
          ].map((c) => ({ ...c, w, h: lineHeight }));
          const inside = (c) => c.x >= area.left && c.x + c.w <= area.right + 60 && c.y >= area.top && c.y + c.h <= area.bottom;
          const spot = candidates.find((c) => inside(c) && !placed.some((p) => overlaps(c, p)));
          if (!spot) return;
          placed.push(spot);
          ctx.fillStyle = opts.color;
          ctx.fillText(raw.name, spot.x, spot.y + lineHeight / 2);
        });
        ctx.restore();
        return;
      }

      // courbes : dernier point non nul, puis on écarte verticalement les étiquettes
      const labels = [];
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden || !ds.label || ds._context) return;
        for (let j = meta.data.length - 1; j >= 0; j -= 1) {
          if (ds.data[j] != null) {
            labels.push({ text: ds.label, color: ds.borderColor, x: meta.data[j].x + 6, y: meta.data[j].y });
            break;
          }
        }
      });
      labels.sort((a, b) => a.y - b.y);
      for (let i = 1; i < labels.length; i += 1) {
        labels[i].y = Math.max(labels[i].y, labels[i - 1].y + lineHeight);
      }
      const overflow = labels.length ? labels[labels.length - 1].y - area.bottom : 0;
      if (overflow > 0) labels.forEach((l) => { l.y -= overflow; });
      labels.forEach((l) => {
        ctx.fillStyle = l.color;
        ctx.fillText(l.text, l.x, l.y);
      });
      ctx.restore();
    },
  };
  Chart.register(directLabels);

  /* Lignes de repère (50 %, diagonale) pour le nuage gentil × méchant. */
  const guides = {
    id: "guides",
    beforeDatasetsDraw(chart, _args, opts) {
      if (!opts || !opts.enabled) return;
      const { ctx, chartArea: a, scales: { x, y } } = chart;
      ctx.save();
      ctx.strokeStyle = opts.color;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x.getPixelForValue(50), a.top);
      ctx.lineTo(x.getPixelForValue(50), a.bottom);
      ctx.moveTo(a.left, y.getPixelForValue(50));
      ctx.lineTo(a.right, y.getPixelForValue(50));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      const lo = Math.max(x.min, y.min), hi = Math.min(x.max, y.max);
      ctx.moveTo(x.getPixelForValue(lo), y.getPixelForValue(lo));
      ctx.lineTo(x.getPixelForValue(hi), y.getPixelForValue(hi));
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = opts.labelColor;
      ctx.font = `600 11px ${Chart.defaults.font.family}`;
      ctx.textAlign = "right";
      ctx.fillText("Fort partout ↗", a.right - 6, a.top + 14);
      ctx.textAlign = "left";
      ctx.fillText("↙ À la peine", a.left + 10, a.bottom - 16);
      ctx.restore();
    },
  };
  Chart.register(guides);

  const charts = [];
  const builders = [];
  const register = (build) => builders.push(build);
  let firstRender = true;
  const renderAll = () => {
    charts.splice(0).forEach((c) => c.destroy());
    const t = theme();
    applyDefaults(t);
    builders.forEach((build) => {
      const chart = build(t);
      if (chart) charts.push(chart);
    });
    firstRender = false;
  };

  /* ---------------------------------------------------------------- nuage gentil × méchant */
  register((t) => {
    const canvas = document.getElementById("scatter");
    const points = readJSON("scatter-data");
    if (!canvas || !points || !points.length) return null;
    const maxWins = Math.max(...points.map((p) => p.wins), 1);
    const radius = (wins) => 6 + 18 * Math.sqrt(wins / maxWins);
    const data = points.map((p) => ({ ...p, r: radius(p.wins) }));
    const xs = data.map((p) => p.x), ys = data.map((p) => p.y);
    const pad = 8;
    const lo = Math.max(0, Math.floor((Math.min(...xs, ...ys) - pad) / 10) * 10);
    const hi = Math.min(100, Math.ceil((Math.max(...xs, ...ys) + pad) / 10) * 10);
    const color = (p) => (p.y >= p.x ? t.villain : t.kind);
    return new Chart(canvas, {
      type: "bubble",
      data: {
        datasets: [{
          label: "Joueurs",
          data,
          backgroundColor: data.map((p) => `${color(p)}b3`),
          borderColor: t.surface,
          borderWidth: 2,
          hoverBorderColor: t.text,
        }],
      },
      options: {
        layout: { padding: { right: 60 } },
        scales: {
          x: axis(t, { min: lo, max: hi, title: { display: true, text: "% de victoires en gentil →", color: t.text2 }, ticks: { color: t.muted, callback: fmtPct } }),
          y: axis(t, { min: lo, max: hi, title: { display: true, text: "% de victoires en méchant →", color: t.text2 }, ticks: { color: t.muted, callback: fmtPct } }),
        },
        plugins: {
          guides: { enabled: true, color: t.muted, labelColor: t.muted },
          directLabels: { enabled: true, mode: "bubble", color: t.text2 },
          tooltip: {
            callbacks: {
              title: (items) => items[0].raw.name,
              label: (item) => {
                const p = item.raw;
                return [
                  `Gentil : ${fmtPct(p.x)} (${p.kind_games} parties)`,
                  `Méchant : ${fmtPct(p.y)} (${p.villain_games} parties)`,
                  `Total : ${p.wins} victoires / ${p.games} (${fmtPct(p.win_pct)})`,
                ];
              },
            },
          },
        },
        onClick: (_e, els) => {
          if (els.length) window.location.href = data[els[0].index].url;
        },
      },
    });
  });

  /* ---------------------------------------------------------------- équilibre des camps par mois */
  register((t) => {
    const canvas = document.getElementById("side-months");
    const d = readJSON("side-months-data");
    if (!canvas || !d || !d.labels.length) return null;
    const bar = { borderRadius: 4, borderSkipped: false, maxBarThickness: 36, borderColor: t.surface, borderWidth: { top: 2 } };
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: d.labels,
        datasets: [
          { label: "Gentils", data: d.kind, backgroundColor: t.kind, ...bar },
          { label: "Méchants", data: d.villain, backgroundColor: t.villain, ...bar },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: axis(t, { stacked: true, grid: { display: false } }),
          y: axis(t, { stacked: true, beginAtZero: true, ticks: { color: t.muted, precision: 0 } }),
        },
        plugins: {
          tooltip: {
            callbacks: {
              footer: (items) => {
                const k = items.find((i) => i.datasetIndex === 0)?.raw ?? 0;
                const v = items.find((i) => i.datasetIndex === 1)?.raw ?? 0;
                return k + v ? `Gentils : ${Math.round((k / (k + v)) * 100)} %` : "";
              },
            },
          },
        },
      },
    });
  });

  /* ---------------------------------------------------------------- course dans le temps */
  const timelineState = { metric: "wins", selected: [], slots: new Map(), initialized: false };

  const assignSlot = (id) => {
    // Couleur stable par joueur : un joueur garde sa couleur quand on en retire un autre.
    if (timelineState.slots.has(id)) return timelineState.slots.get(id);
    const used = new Set(timelineState.slots.values());
    for (let i = 0; i < MAX_HIGHLIGHT; i += 1) {
      if (!used.has(i)) { timelineState.slots.set(id, i); return i; }
    }
    return 0;
  };

  const lastValue = (arr) => { for (let i = arr.length - 1; i >= 0; i -= 1) if (arr[i] != null) return arr[i]; return null; };

  register((t) => {
    const canvas = document.getElementById("timeline");
    const d = readJSON("timeline-data");
    if (!canvas || !d || !d.labels.length) return null;
    const { metric } = timelineState;

    if (!timelineState.initialized) {
      timelineState.initialized = true;
      timelineState.selected = [...d.players]
        .sort((a, b) => (lastValue(b.series.wins) ?? 0) - (lastValue(a.series.wins) ?? 0))
        .slice(0, MAX_HIGHLIGHT)
        .map((p) => p.id);
      timelineState.selected.forEach(assignSlot);
    }
    const selected = new Set(timelineState.selected);

    // Sélecteur de joueurs
    const picker = document.querySelector('[data-series-picker="timeline"]');
    if (picker) {
      picker.replaceChildren(...[...d.players]
        .sort((a, b) => (lastValue(b.series[metric]) ?? -1) - (lastValue(a.series[metric]) ?? -1))
        .map((p) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "chip";
          const on = selected.has(p.id);
          btn.setAttribute("aria-pressed", String(on));
          if (on) btn.style.setProperty("--sw", t.series[timelineState.slots.get(p.id)]);
          btn.innerHTML = `<span class="swatch"></span>`;
          btn.append(document.createTextNode(p.name));
          btn.addEventListener("click", () => {
            if (selected.has(p.id)) {
              timelineState.selected = timelineState.selected.filter((x) => x !== p.id);
              timelineState.slots.delete(p.id);
            } else {
              if (timelineState.selected.length >= MAX_HIGHLIGHT) {
                const removed = timelineState.selected.shift();
                timelineState.slots.delete(removed);
              }
              timelineState.selected.push(p.id);
              assignSlot(p.id);
            }
            renderAll();
          });
          return btn;
        }));
    }

    const context = d.players.filter((p) => !selected.has(p.id)).map((p) => ({
      label: p.name,
      _context: true,
      data: p.series[metric],
      borderColor: t.surface3,
      borderWidth: 1.5,
      pointRadius: 0,
      pointHoverRadius: 0,
      tension: 0.25,
      spanGaps: true,
      order: 2,
    }));
    const highlighted = d.players.filter((p) => selected.has(p.id)).map((p) => {
      const color = t.series[assignSlot(p.id)];
      return {
        label: p.name,
        data: p.series[metric],
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2.5,
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderColor: t.surface,
        pointHoverBorderWidth: 2,
        tension: 0.25,
        spanGaps: true,
        order: 1,
      };
    });

    const isPct = metric === "winrate";
    return new Chart(canvas, {
      type: "line",
      data: { labels: d.labels.map(fmtDay), datasets: [...context, ...highlighted] },
      options: {
        layout: { padding: { right: 80 } },
        interaction: { mode: "index", intersect: false },
        scales: {
          x: axis(t, { grid: { display: false }, ticks: { color: t.muted, maxRotation: 0, autoSkipPadding: 24 } }),
          y: axis(t, {
            beginAtZero: metric !== "elo",
            suggestedMax: isPct ? 100 : undefined,
            ticks: { color: t.muted, precision: 0, callback: isPct ? fmtPct : undefined },
          }),
        },
        plugins: {
          directLabels: { enabled: true },
          tooltip: {
            filter: (item) => !item.dataset._context,
            itemSort: (a, b) => (b.raw ?? -Infinity) - (a.raw ?? -Infinity),
            callbacks: { label: (item) => ` ${item.dataset.label} : ${isPct ? fmtPct(item.raw) : item.raw}` },
          },
        },
      },
    });
  });

  /* ---------------------------------------------------------------- profil joueur */
  const playerState = { metric: "elo" };
  register((t) => {
    const canvas = document.getElementById("player-evo");
    const d = readJSON("player-timeline");
    if (!canvas || !d || !d.labels.length) return null;
    const isPct = playerState.metric === "winrate";
    const values = d[playerState.metric];
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: d.labels.map((l, i) => `#${i + 1} · ${fmtDay(l)}`),
        datasets: [{
          label: isPct ? "% victoires" : "Elo",
          data: values,
          borderColor: t.accent,
          backgroundColor: `${t.accent}22`,
          fill: true,
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: t.accent,
          pointHoverBorderColor: t.surface,
          pointHoverBorderWidth: 2,
        }],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: axis(t, { grid: { display: false }, ticks: { display: false } }),
          y: axis(t, { suggestedMin: isPct ? 0 : undefined, suggestedMax: isPct ? 100 : undefined, ticks: { color: t.muted, callback: isPct ? fmtPct : undefined } }),
        },
        plugins: {
          tooltip: {
            displayColors: false,
            callbacks: {
              label: (item) => `${isPct ? "Victoires" : "Elo"} : ${isPct ? fmtPct(item.raw) : item.raw}`,
              afterLabel: (item) => (d.results[item.dataIndex] ? "✓ Victoire" : "✗ Défaite"),
            },
          },
        },
      },
    });
  });

  register((t) => {
    const canvas = document.getElementById("player-months");
    const d = readJSON("player-monthly");
    if (!canvas || !d || !d.labels.length) return null;
    const bar = { borderRadius: 4, borderSkipped: false, maxBarThickness: 28, borderColor: t.surface, borderWidth: { top: 2 } };
    return new Chart(canvas, {
      type: "bar",
      data: {
        labels: d.labels,
        datasets: [
          { label: "Victoires", data: d.wins, backgroundColor: t.accent, ...bar },
          { label: "Défaites", data: d.losses, backgroundColor: t.surface3, ...bar },
        ],
      },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: {
          x: axis(t, { stacked: true, grid: { display: false } }),
          y: axis(t, { stacked: true, beginAtZero: true, ticks: { color: t.muted, precision: 0 } }),
        },
      },
    });
  });

  /* ---------------------------------------------------------------- boutons d'indicateur */
  document.querySelectorAll("[data-chart-switch]").forEach((group) => {
    const state = group.dataset.chartSwitch === "timeline" ? timelineState : playerState;
    group.querySelectorAll("[data-metric]").forEach((btn, _, all) => {
      btn.addEventListener("click", () => {
        all.forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
        state.metric = btn.dataset.metric;
        renderAll();
      });
    });
  });

  document.addEventListener("tb:themechange", renderAll);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
  renderAll();
})();
