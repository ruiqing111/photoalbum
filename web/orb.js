/* 照片「表盘」视图：可以拖着走的蜂窝网格，靠近画面中心的照片自动放大。
 *
 * 不是固定 101 张的转盘 —— 照片按行排成一张大平面，鼠标/手指拖动改变
 * panX/panY，像拖动一张无限大的照片墙；每帧只渲染可视范围内的节点，
 * 拖到边缘时自动向接口要下一页，所以两万张也能一直看下去。
 * 画面中心按距离做一个透镜：越靠中心越大、越清晰，越靠边越小、越淡。
 */
(function () {
  const PAGE_SIZE = 200;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  let cur = null;                       // 当前挂载的实例，同一时间只会有一个

  function mount(grid, opts) {
    if (cur && cur.stop) cur.stop();
    grid.innerHTML = "";
    const stage = document.createElement("div");
    stage.className = "orb-stage";
    const hint = document.createElement("div");
    hint.className = "orb-hint";
    hint.textContent = "拖动浏览 · 中心自动放大 · 点击打开";
    const cap = document.createElement("div");
    cap.className = "orb-cap";
    grid.append(stage, hint, cap);

    const st = {
      grid, stage, cap,
      items: (opts.items || []).slice(),
      total: Math.max(opts.total || 0, (opts.items || []).length),
      pageSize: opts.pageSize || PAGE_SIZE,
      loadPage: opts.loadPage || null,
      onOpen: opts.onOpen || null,
      nodes: new Map(),
      panX: 0, panY: 0, vx: 0, vy: 0,
      dragging: false, moved: 0, lastX: 0, lastY: 0, lastT: 0,
      raf: 0, loading: false,
      size: 92, colStep: 96, rowStep: 84, pad: 24, cols: 8,
      ro: null, sizeRaf: 0,
    };
    cur = st;

    function measure() {
      const w = grid.clientWidth, h = grid.clientHeight;
      st.size = clamp(Math.min(w / 9.5, h / 6.2), 56, 124);
      st.colStep = st.size * 1.04;
      st.rowStep = st.size * 0.88;
      st.pad = st.size * 0.55;
      st.cols = Math.max(4, Math.floor((w - st.pad * 2) / st.colStep));
      st.nodes.forEach(o => {
        o.el.style.width = o.el.style.height = st.size + "px";
      });
    }

    function plane() {
      const rows = Math.ceil(st.items.length / st.cols);
      return {
        rows,
        width: st.pad * 2 + st.cols * st.colStep + st.colStep * 0.5,
        height: st.pad * 2 + rows * st.rowStep + st.rowStep * 0.5,
      };
    }

    function clampPan() {
      const w = grid.clientWidth, h = grid.clientHeight;
      const p = plane();
      st.panX = clamp(st.panX, Math.min(0, w - p.width), 0);
      st.panY = clamp(st.panY, Math.min(0, h - p.height), 0);
    }

    function makeNode(idx, it) {
      const el = document.createElement("button");
      el.className = "orb-node";
      el.dataset.i = String(idx);
      el.style.width = el.style.height = st.size + "px";
      el.innerHTML = `<img src="/api/thumb/${it.id}?size=s" alt="" decoding="async">`;
      st.stage.appendChild(el);
      return { el, it };
    }

    function draw() {
      const w = grid.clientWidth, h = grid.clientHeight;
      if (!w || !h) return;
      const p = plane();
      const rowTop = Math.floor((-st.panY - st.pad) / st.rowStep) - 1;
      const rowBottom = rowTop + Math.ceil(h / st.rowStep) + 3;
      const first = Math.max(0, rowTop * st.cols);
      const last = Math.min(st.items.length, (rowBottom + 1) * st.cols);

      // 移除跑出可视范围（含一行余量）的节点，避免无限堆积 DOM
      st.nodes.forEach((o, idx) => {
        if (idx < first - st.cols * 2 || idx > last + st.cols * 2) {
          o.el.remove();
          st.nodes.delete(idx);
        }
      });

      const cx = w / 2, cy = h / 2;
      const R = Math.min(w, h) * 0.46;
      for (let idx = first; idx < last; idx++) {
        const it = st.items[idx];
        if (!it) continue;
        let o = st.nodes.get(idx);
        if (!o) {
          o = makeNode(idx, it);
          st.nodes.set(idx, o);
        }
        const row = Math.floor(idx / st.cols);
        const col = idx % st.cols;
        const x = st.panX + st.pad + col * st.colStep + (row % 2 ? st.colStep * 0.5 : 0);
        const y = st.panY + st.pad + row * st.rowStep;
        // 透镜：离画面中心越近，放得越大、越不透明
        const d = Math.hypot(x + st.size / 2 - cx, y + st.size / 2 - cy);
        const lens = clamp(1 - d / R, 0, 1);
        const scale = 0.68 + 0.72 * Math.pow(lens, 1.45);
        o.el.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) scale(${scale.toFixed(3)})`;
        o.el.style.opacity = (0.34 + 0.66 * Math.pow(lens, 1.05)).toFixed(3);
        o.el.style.zIndex = String(10 + Math.round(scale * 10));
      }
      st.cap.textContent = st.items.length < st.total
        ? `共 ${st.total} 张 · 拖动加载更多（已载入 ${st.items.length} 张）`
        : `共 ${st.total} 张`;
    }

    function schedule() {
      if (st.raf) return;
      st.raf = requestAnimationFrame(step);
    }

    function step() {
      st.raf = 0;
      if (!grid.isConnected) { stop(); return; }
      if (!st.dragging) {
        if (Math.abs(st.vx) > 0.05 || Math.abs(st.vy) > 0.05) {
          st.panX += st.vx; st.panY += st.vy;
          st.vx *= 0.93; st.vy *= 0.93;
          clampPan();
          maybeLoad();
        } else {
          st.vx = st.vy = 0;
        }
      }
      draw();
      if (Math.abs(st.vx) > 0.05 || Math.abs(st.vy) > 0.05 || st.dragging) schedule();
    }

    async function maybeLoad() {
      if (st.loading || !st.loadPage || st.items.length >= st.total) return;
      const h = grid.clientHeight;
      const p = plane();
      const bottom = Math.min(0, h - p.height);
      const nearBottom = st.panY <= bottom + st.rowStep * 3;
      // 照片墙还很长、又没拖到底部附近时，先不打扰接口
      if (p.height > h + st.rowStep * 3 && !nearBottom) return;
      st.loading = true;
      const page = Math.floor(st.items.length / st.pageSize) + 1;
      try {
        const arr = await st.loadPage(page);
        if (!arr || !arr.length) { st.total = st.items.length; return; }
        st.items = st.items.concat(arr);
        schedule();
      } catch (e) {
        // 加载失败不打断浏览，下一次拖动再试
      } finally {
        st.loading = false;
      }
    }

    function down(e) {
      if (e.button !== undefined && e.button !== 0) return;
      st.dragging = true; st.moved = 0;
      st.lastX = e.clientX; st.lastY = e.clientY;
      st.lastT = performance.now();
      st.vx = st.vy = 0;
      grid.classList.add("dragging");
      try { grid.setPointerCapture(e.pointerId); } catch (_) {}
    }
    function move(e) {
      if (!st.dragging) return;
      const dx = e.clientX - st.lastX, dy = e.clientY - st.lastY;
      st.lastX = e.clientX; st.lastY = e.clientY;
      st.lastT = performance.now();
      st.moved += Math.abs(dx) + Math.abs(dy);
      st.panX += dx; st.panY += dy;
      st.vx = dx; st.vy = dy;
      clampPan();
      maybeLoad();
      schedule();
      e.preventDefault();
    }
    function up(e) {
      if (!st.dragging) return;
      st.dragging = false;
      if (performance.now() - st.lastT > 90) st.vx = st.vy = 0;
      grid.classList.remove("dragging");
      try { grid.releasePointerCapture(e.pointerId); } catch (_) {}
      schedule();
    }
    function wheel(e) {
      if (!e.deltaY && !e.deltaX) return;
      e.preventDefault();
      st.panX -= e.deltaX;
      st.panY -= e.deltaY;
      clampPan();
      maybeLoad();
      st.vx = st.vy = 0;
      schedule();
    }

    grid.addEventListener("pointerdown", down);
    grid.addEventListener("pointermove", move);
    grid.addEventListener("pointerup", up);
    grid.addEventListener("pointercancel", up);
    grid.addEventListener("wheel", wheel, { passive: false });
    grid.addEventListener("click", e => {
      const n = e.target.closest(".orb-node");
      if (!n) return;
      if (st.moved > 8) return;          // 拖完手滑一下，不算点击
      if (st.onOpen) st.onOpen(Number(n.dataset.i));
    });

    function stop() {
      if (st.raf) cancelAnimationFrame(st.raf);
      st.raf = 0;
      if (st.ro) st.ro.disconnect();
      clearTimeout(st.sizeRaf);
    }
    st.stop = stop;

    st.ro = new ResizeObserver(() => {
      if (st.sizeRaf) return;
      st.sizeRaf = requestAnimationFrame(() => {
        st.sizeRaf = 0;
        measure();
        clampPan();
        draw();
      });
    });
    st.ro.observe(grid);

    measure();
    // 初始把第一排放在画面上部，留一点上边距
    st.panX = Math.min(0, (grid.clientWidth - plane().width) / 2);
    clampPan();
    draw();
  }

  window.OrbLayout = {
    mount,
    items: () => (cur ? cur.items : []),
  };
})();
