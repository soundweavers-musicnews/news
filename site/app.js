(() => {
  let allItems = [];
  let activeCategory = "全部";
  let activeMonth = "all";
  let searchQuery = "";

  const toDateKey = (iso) => {
    if (!iso) return "未知日期";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso).slice(0, 10);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  };

  const escapeHtml = (str) =>
    String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  // Theme toggle (matches soundweavers-music.github.io)
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "nextdoor";
    const next = cur === "dark" ? "nextdoor" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });

  const renderFeatured = (item) => {
    const videoEl = document.getElementById("featured-video");
    const placeholderEl = document.getElementById("video-placeholder");

    if (item.video_url) {
      videoEl.src = item.video_url;
      videoEl.classList.remove("hidden");
      placeholderEl.classList.add("hidden");
    } else {
      videoEl.classList.add("hidden");
      placeholderEl.classList.remove("hidden");
    }

    document.getElementById("featured-category").textContent = item.category || "音樂科技";
    document.getElementById("featured-date").textContent = toDateKey(item.publish_at || item.published_at);
    document.getElementById("featured-source").textContent = item.source || "";
    document.getElementById("featured-title").textContent = item.title_zh || item.title;
    document.getElementById("featured-summary").textContent = item.summary || "";
    document.getElementById("featured-tech").textContent = item.tech_analysis || "";
    document.getElementById("featured-link").href = item.url || "#";

    const hlEl = document.getElementById("featured-highlights");
    hlEl.innerHTML = "";
    (item.highlights || []).forEach((h) => {
      const li = document.createElement("li");
      li.textContent = h;
      hlEl.appendChild(li);
    });
  };

  const renderMonthOptions = () => {
    const select = document.getElementById("month-filter");
    const months = [...new Set(allItems.map((i) => toDateKey(i.publish_at || i.published_at).slice(0, 7)))].sort().reverse();
    select.innerHTML = `<option value="all">所有月份（${allItems.length} 則）</option>`;
    months.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      select.appendChild(opt);
    });
  };

  const renderFilters = () => {
    const cats = ["全部", ...new Set(allItems.map((i) => i.category || "音樂科技"))];
    const container = document.getElementById("category-filters");
    container.innerHTML = "";
    cats.forEach((cat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `chip ${cat === activeCategory ? "active" : ""}`;
      btn.textContent = cat;
      btn.addEventListener("click", () => {
        activeCategory = cat;
        renderFilters();
        renderTimeline();
      });
      container.appendChild(btn);
    });
  };

  const renderTimeline = () => {
    const timeline = document.getElementById("news-timeline");
    const countEl = document.getElementById("result-count");
    timeline.innerHTML = "";

    const q = searchQuery.trim().toLowerCase();
    const filtered = allItems.filter((item) => {
      const dateKey = toDateKey(item.publish_at || item.published_at);
      if (activeMonth !== "all" && !dateKey.startsWith(activeMonth)) return false;
      if (activeCategory !== "全部" && (item.category || "音樂科技") !== activeCategory) return false;
      if (!q) return true;
      const hay = `${dateKey} ${item.title_zh || ""} ${item.title || ""} ${item.summary || ""} ${item.tech_analysis || ""} ${item.source || ""} ${(item.keywords || []).join(" ")}`.toLowerCase();
      return hay.includes(q);
    });

    countEl.textContent = `顯示 ${filtered.length} / ${allItems.length} 則`;

    if (!filtered.length) {
      timeline.innerHTML = `<p class="meta-text">找不到符合條件的新聞，請嘗試其他關鍵字或篩選條件。</p>`;
      return;
    }

    // Group by publish date (descending)
    const groups = new Map();
    filtered.forEach((item) => {
      const day = toDateKey(item.publish_at || item.published_at);
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(item);
    });

    const sortedDays = [...groups.keys()].sort().reverse();
    sortedDays.forEach((day) => {
      const dayItems = groups.get(day);
      const section = document.createElement("div");
      section.className = "date-group";

      section.innerHTML = `
        <div class="date-group-header">
          <h2>${escapeHtml(day)}</h2>
          <span class="date-group-count">${dayItems.length} 則報導</span>
        </div>
      `;

      const list = document.createElement("div");
      list.className = "date-list";

      dayItems.forEach((item) => {
        const row = document.createElement("article");
        row.className = "news-row";

        const hlHtml = (item.highlights || [])
          .map((h) => `<li>${escapeHtml(h)}</li>`)
          .join("");

        row.innerHTML = `
          <div class="news-row-top">
            <div class="news-row-meta">
              <span class="tag-pill">${escapeHtml(item.category || "音樂科技")}</span>
              <span class="meta-text">${escapeHtml(item.source || "")}</span>
            </div>
            <a class="source-link" href="${escapeHtml(item.url || "#")}" target="_blank" rel="noopener">原文報導 ↗</a>
          </div>
          <h3 class="news-row-title">${escapeHtml(item.title_zh || item.title)}</h3>
          <p class="news-row-summary">${escapeHtml(item.summary || "")}</p>
          <details class="news-row-details">
            <summary>展開重點整理與技術分析</summary>
            <div class="news-row-details-body">
              <strong>重點整理</strong>
              <ul>${hlHtml}</ul>
              <strong>技術分析</strong>
              <p>${escapeHtml(item.tech_analysis || "")}</p>
            </div>
          </details>
        `;

        if (item.video_url) {
          row.style.cursor = "pointer";
          row.addEventListener("click", (e) => {
            if (e.target.closest("a, details, summary")) return;
            renderFeatured(item);
            window.scrollTo({ top: 0, behavior: "smooth" });
          });
        }

        list.appendChild(row);
      });

      section.appendChild(list);
      timeline.appendChild(section);
    });
  };

  async function init() {
    try {
      const resp = await fetch("./data/news.json", { cache: "no-store" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();

      const params = new URLSearchParams(window.location.search);
      const previewAll = params.get("preview") === "all";
      const nowMs = Date.now();
      const rawItems = data.items || [];

      allItems = rawItems
        .filter((item) => {
          if (previewAll || !item.publish_at) return true;
          const pubMs = new Date(item.publish_at).getTime();
          return Number.isNaN(pubMs) || pubMs <= nowMs;
        })
        .sort((a, b) => {
          const ta = new Date(a.publish_at || a.published_at || 0).getTime();
          const tb = new Date(b.publish_at || b.published_at || 0).getTime();
          return tb - ta;
        });

      if (allItems.length) {
        const latestDate = toDateKey(allItems[0].publish_at || allItems[0].published_at);
        document.getElementById("updated-at").textContent = `更新：${latestDate}`;
        const featured = allItems.find((i) => i.video_url) || allItems[0];
        renderFeatured(featured);
      } else if (data.updated_at) {
        document.getElementById("updated-at").textContent = `更新：${toDateKey(data.updated_at)}`;
      }
      renderMonthOptions();
      renderFilters();
      renderTimeline();
    } catch (err) {
      document.getElementById("featured-title").textContent = "尚未產生新聞資料";
      document.getElementById("featured-summary").textContent = `請先執行 python pipeline/run_daily.py 產生每日播報資料。（${err.message}）`;
    }
  }

  document.getElementById("search-input").addEventListener("input", (e) => {
    searchQuery = e.target.value;
    renderTimeline();
  });

  document.getElementById("month-filter").addEventListener("change", (e) => {
    activeMonth = e.target.value;
    renderTimeline();
  });

  init();
})();
