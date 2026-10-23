/* 环形照片布局（Apple Watch 式）：中心精选最大最清晰，外圈逐级变小、
 * 变淡并轻微虚化；整张圆可以拖动旋转，松手带惯性，滚轮（触控板）缩放。
 *
 * 所有位置都由 requestAnimationFrame 里写 transform 完成，不碰 left/top，
 * 因此 100 个节点也只在拖动/缩放时才产生合成层更新，静态时零开销。
 */
(function () {
  // radius：相对半径（0 为圆心）；size：基准像素；speed：拖动时的跟手系数。
  // 半径与尺寸是按「相邻两圈刚好不压住」算过的：改其中一个就要连着改另一个。
  const RINGS = [
    { r: 0.000, size: 176, opacity: 1.00, blur: 0.0, speed: 0.00 },
    { r: 0.320, size: 102, opacity: 0.98, blur: 0.0, speed: 0.32 },
    { r: 0.530, size: 77, opacity: 0.90, blur: 0.3, speed: 0.55 },
    { r: 0.700, size: 59, opacity: 0.76, blur: 0.7, speed: 0.75 },
    { r: 0.840, size: 46, opacity: 0.58, blur: 1.2, speed: 0.95 },
    { r: 0.950, size: 36, opacity: 0.40, blur: 1.8, speed: 1.10 },
  ];
  const COUNTS = [1, 6, 12, 20, 28, 34];
  const CAP = COUNTS.reduce((a, b) => a + b, 0);
  const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function render(grid, items, opts = {}) {
    // 同一个容器再次渲染（例如换月份、换筛选）时，先把上一轮的动画循环停掉
    if (grid._orbStop) { grid._orbStop(); grid._orbStop = null; }
    grid.innerHTML = "";
    const shown = items.slice(0, CAP);
    if (!shown.length) {
      grid.innerHTML = '<div class="empty"><b>这里还没有照片</b></div>';
      return;
    }

    // 精选（收藏或高画质）优先占圆心与内圈，其余按原顺序铺外圈
    const picked = [], others = [];
    shown.forEach((it, i) => ((it.is_favorite || (it.quality || 0) >= 72) ? picked : others).push(i));
    const order = picked.concat(others);

    const stage = document.createElement("div");
    stage.className = "orb-stage";
    grid.appendChild(stage);

    // 按环分配：每环的容量固定，不够就往后顺延
    const take = [];
    let left = order.length;
    COUNTS.forEach(n => { const k = Math.min(n, left); take.push(k); left -= k; });

    const nodes = [];
    let cur = 0;
    RINGS.forEach((ring, ri) => {
      const n = take[ri];
      for (let j = 0; j < n; j++) {
        const idx = order[cur + j];
        const it = shown[idx];
        const node = document.createElement("button");
        node.className = "orb-node" + (ri === 0 ? " is-center" : "");
        node.dataset.i = idx;
        node.style.opacity = ring.opacity;
        node.style.zIndex = String(90 - ri * 10);
        if (ring.blur) node.style.filter = `blur(${ring.blur}px)`;
        node.title = it.name || "";
        node.innerHTML = `<img src="/api/thumb/${it.id}?size=s" alt="" decoding="async">`
          + (it.is_favorite ? '<span class="orb-fav">♥</span>' : "");
        stage.appendChild(node);
        nodes.push({ node, ring: ri, base: (j / n) * Math.PI * 2 + ri * 0.42, sz: ring.size });
      }
      cur += n;
    });

    const hint = document.createElement("div");
    hint.className = "orb-hint";
    hint.textContent = REDUCE ? "" : "拖动旋转 · 滚轮缩放";
    const cap = document.createElement("div");
    cap.className = "orb-cap";
    cap.textContent = items.length > CAP ? `共 ${items.length} 张 · 环形展示前 ${CAP} 张` : "";
    grid.append(hint, cap);

    const rot = RINGS.map(() => 0);
    let vel = 0, zoom = 1, tzoom = 1, raf = 0, drag = false;
    let lastX = 0, moved = 0, lastT = 0;
    let unit = 1;
    let ro = null, sizeRaf = 0;

    function applySizes() {
      const w = grid.clientWidth || 700;
      // 小窗口下缩得比 0.55 更小：外圈 34 张的周长是固定的，
      // 节点不跟着缩就会互相压住 —— 之前「挤在一起」就是没有这层比例。
      unit = clamp(w / 900, 0.30, 1.2);
      nodes.forEach(o => {
        o.sz = Math.round(RINGS[o.ring].size * unit);
        o.node.style.width = o.sz + "px";
        o.node.style.height = o.sz + "px";
      });
      draw();
    }

    function draw() {
      const w = grid.clientWidth, h = grid.clientHeight;
      if (!w || !h) {
        // 窗口被遮挡/刚插入时尺寸可能是 0，别把节点全丢在左上角：
        // 稍后重试一次（用 setTimeout，rAF 在隐藏窗口里不触发）
        clearTimeout(grid._orbRetry);
        grid._orbRetry = setTimeout(() => { if (grid.isConnected) applySizes(); }, 120);
        return;
      }
      const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2;
      nodes.forEach(o => {
        const ring = RINGS[o.ring];
        const ang = o.base + rot[o.ring];
        const x = Math.cos(ang) * R * ring.r * zoom;
        const y = Math.sin(ang) * R * ring.r * zoom;
        o.node.style.transform =
          `translate3d(${(cx + x - o.sz / 2).toFixed(1)}px, ` +
          `${(cy + y - o.sz / 2).toFixed(1)}px, 0) scale(${zoom.toFixed(3)})`;
      });
    }

    function step() {
      raf = 0;
      if (!grid.isConnected) { if (ro) ro.disconnect(); return; }
      if (!drag && Math.abs(vel) > 0.0004) {
        for (let i = 1; i < RINGS.length; i++) rot[i] += vel * RINGS[i].speed;
        vel *= REDUCE ? 0 : 0.945;          // 松手后的惯性衰减
      } else if (!drag) {
        vel = 0;
      }
      if (Math.abs(zoom - tzoom) > 0.0015) zoom += (tzoom - zoom) * 0.18;
      draw();
      if ((!drag && Math.abs(vel) > 0.0004) || Math.abs(zoom - tzoom) > 0.0015) schedule();
    }
    function schedule() { if (!raf) raf = requestAnimationFrame(step); }

    function down(e) {
      if (e.button !== undefined && e.button !== 0) return;
      drag = true; moved = 0; lastX = e.clientX; vel = 0;
      lastT = performance.now();
      grid.classList.add("dragging");
      try { grid.setPointerCapture(e.pointerId); } catch (_) {}
    }
    function move(e) {
      if (!drag) return;
      const dx = e.clientX - lastX;
      lastX = e.clientX;
      lastT = performance.now();
      moved += Math.abs(dx);
      const R = Math.max(220, Math.min(grid.clientWidth, grid.clientHeight) / 2);
      const d = (dx / R) * 1.35;
      for (let i = 1; i < RINGS.length; i++) rot[i] += d * RINGS[i].speed;
      vel = d;
      schedule();
      e.preventDefault();
    }
    function up(e) {
      if (!drag) return;
      drag = false;
      // 停手超过 90ms 再松开，不该继续滑 —— 否则轻轻一放也会甩出去
      if (performance.now() - lastT > 90) vel = 0;
      grid.classList.remove("dragging");
      try { grid.releasePointerCapture(e.pointerId); } catch (_) {}
      schedule();
    }
    function wheel(e) {
      if (!e.deltaY) return;
      e.preventDefault();
      tzoom = clamp(tzoom * (1 - e.deltaY * 0.0009), 0.72, 1.32);
      schedule();
    }

    grid.addEventListener("pointerdown", down);
    grid.addEventListener("pointermove", move);
    grid.addEventListener("pointerup", up);
    grid.addEventListener("pointercancel", up);
    grid.addEventListener("wheel", wheel, { passive: false });
    // 拖动超过 8px 就当成旋转，不再触发打开照片
    grid.addEventListener("click", e => {
      const node = e.target.closest(".orb-node");
      if (!node || moved > 8) return;
      if (opts.onOpen) opts.onOpen(Number(node.dataset.i));
    });

    grid._orbStop = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      drag = false;
      clearTimeout(grid._orbRetry);
      if (ro) ro.disconnect();
    };

    ro = new ResizeObserver(() => {
      if (sizeRaf) return;
      sizeRaf = requestAnimationFrame(() => { sizeRaf = 0; applySizes(); });
    });
    ro.observe(grid);
    applySizes();
  }

  window.OrbLayout = { render, CAP };
})();
