/* Time Bomb Stats — interactions communes (sans dépendance). */
(() => {
  "use strict";

  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- thème clair / sombre ---------- */
  const root = document.documentElement;
  const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;
  const currentTheme = () => root.dataset.theme || (systemDark() ? "dark" : "light");

  $$("[data-theme-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("tb-theme", next); } catch (e) { /* stockage indisponible */ }
      document.dispatchEvent(new CustomEvent("tb:themechange"));
    });
  });

  /* ---------- confirmations ---------- */
  $$("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  /* ---------- selects qui soumettent leur formulaire ---------- */
  $$("select[data-autosubmit]").forEach((select) => {
    select.addEventListener("change", () => {
      // évite d'envoyer deux paramètres "p" quand on choisit un mois
      select.form.requestSubmit();
    });
  });

  /* ---------- filtre texte sur une liste ---------- */
  $$("[data-filter-target]").forEach((input) => {
    const target = document.querySelector(input.dataset.filterTarget);
    if (!target) return;
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      $$("[data-name]", target).forEach((el) => {
        el.hidden = q !== "" && !el.dataset.name.includes(q);
      });
    });
  });

  /* ---------- tableaux triables ---------- */
  $$("table[data-sortable]").forEach((table) => {
    const headers = $$("th", table.tHead);
    headers.forEach((th, index) => {
      if (!th.dataset.sort) return;
      th.tabIndex = 0;
      const sort = () => {
        const desc = th.getAttribute("aria-sort") !== "descending";
        headers.forEach((h) => h.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", desc ? "descending" : "ascending");
        const body = table.tBodies[0];
        const rows = Array.from(body.rows);
        const value = (row) => {
          const cell = row.cells[index];
          const raw = cell?.dataset.value ?? cell?.textContent.trim() ?? "";
          if (th.dataset.sort === "num") {
            const n = parseFloat(String(raw).replace(",", ".").replace(/[^\d.-]/g, ""));
            return Number.isNaN(n) ? -Infinity : n;
          }
          return raw.toLowerCase();
        };
        rows.sort((a, b) => {
          const va = value(a), vb = value(b);
          const cmp = typeof va === "number" ? va - vb : va.localeCompare(vb, "fr");
          return desc ? -cmp : cmp;
        });
        rows.forEach((row) => body.appendChild(row));
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });
  });

  /* ---------- saisie d'une partie : compteur des camps ---------- */
  const counter = document.querySelector("[data-team-count]");
  if (counter) {
    const hint = document.querySelector("[data-team-hint]");
    const expected = { 4: "1 ou 2", 5: "2", 6: "2", 7: "2 ou 3", 8: "3" };
    const update = () => {
      const rows = $$("[data-roster-row]");
      let villains = 0;
      rows.forEach((row) => {
        const checked = row.querySelector('input[type="radio"][name^="role_"]:checked');
        const role = checked ? checked.value : "kind";
        row.dataset.role = role;
        if (role === "villain") villains += 1;
      });
      counter.querySelector('[data-count="kind"]').textContent = rows.length - villains;
      counter.querySelector('[data-count="villain"]').textContent = villains;
      if (hint) {
        const exp = expected[rows.length];
        hint.textContent = exp ? `À ${rows.length} joueurs, il y a normalement ${exp} méchant(s).` : "";
      }
    };
    document.addEventListener("change", (e) => { if (e.target.name?.startsWith("role_")) update(); });
    update();
  }

  /* ---------- sélection des joueurs à ajouter ---------- */
  const picker = document.getElementById("picker");
  const selectedCount = document.querySelector("[data-selected-count]");
  if (picker && selectedCount) {
    const refresh = () => {
      const n = $$("input:checked", picker).length;
      selectedCount.textContent = n ? `(${n})` : "";
    };
    picker.addEventListener("change", refresh);
    refresh();
  }

  /* ---------- matrice des duos : même équipe / face à face ---------- */
  const matrix = document.querySelector("[data-matrix]");
  if (matrix) {
    const names = $$("thead th", matrix).map((th) => th.textContent.trim());
    const paint = (mode) => {
      $$("td.heat", matrix).forEach((td) => {
        const n = Number(td.dataset[mode === "same" ? "nSame" : "nVs"]);
        const value = parseFloat(td.dataset[mode]);
        const row = td.parentElement.querySelector("th").textContent.trim();
        const col = names[td.cellIndex];
        if (!n) {
          td.classList.add("none");
          td.textContent = "·";
          td.dataset.side = "none";
          td.style.removeProperty("--t");
          td.title = `${row} et ${col} : aucune partie ${mode === "same" ? "ensemble" : "l'un contre l'autre"}`;
          return;
        }
        const t = Math.max(-1, Math.min(1, (value - 50) / 40));
        td.classList.remove("none");
        td.textContent = Math.round(value);
        td.dataset.side = t >= 0 ? "hi" : "lo";
        td.style.setProperty("--t", Math.abs(t).toFixed(2));
        td.title = mode === "same"
          ? `${row} avec ${col} : ${Math.round(value)} % de victoires en ${n} partie(s) dans la même équipe`
          : `${row} contre ${col} : ${Math.round(value)} % de victoires en ${n} duel(s)`;
      });
    };
    $$("[data-matrix-switch] [data-mode]").forEach((btn, _, all) => {
      btn.addEventListener("click", () => {
        all.forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
        paint(btn.dataset.mode);
      });
    });
    paint("same");
  }
})();
