/* 本地相册 · 前端单页应用（Apple Photos 风格） */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const content = $("#content");

/* 图片解码完再淡入：从移动硬盘一张张读出来时不会「啪」地跳出来 */
content.addEventListener("load", e => {
  if (e.target.tagName === "IMG") e.target.classList.add("in");
}, true);
content.addEventListener("error", e => {
  if (e.target.tagName === "IMG") e.target.classList.add("in");
}, true);
function markLoadedImages() {
  requestAnimationFrame(() => content.querySelectorAll("img").forEach(im => {
    if (im.complete) im.classList.add("in");
  }));
}

const api = url => fetch(url).then(r =>
  r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || r.statusText)).catch(() => Promise.reject(r.statusText)));
const post = (url, body) => fetch(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {})
}).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || r.statusText)));

function toast(msg, ms = 2800) {
  const t = $("#toast");
  // 导入进度每 900ms 刷一次；内容没变就别重写 DOM，
  // 否则 CSS 动画每次都从头播，看着像在闪。
  if (t.innerHTML !== msg) t.innerHTML = msg;
  t.classList.add("show");
  clearTimeout(t._tm); t._tm = setTimeout(() => t.classList.remove("show"), ms);
}
/* 危险操作完成后给一条带「撤销」的提示：比事后去翻日志更容易被用起来 */
function toastUndo(msg, ms = 7000) {
  const t = $("#toast");
  const canUndo = msg.indexOf("彻底删除") < 0;
  t.innerHTML = `<span>${msg}</span>` +
    (canUndo ? `<button class="toast-act" id="toast-undo">撤销</button>` : "");
  t.classList.add("show");
  clearTimeout(t._tm);
  const b = $("#toast-undo");
  if (b) b.onclick = () => { t.classList.remove("show"); undoLast(); };
  t._tm = setTimeout(() => t.classList.remove("show"), ms);
}
async function undoLast() {
  try {
    const r = await post("/api/ops/undo");
    if (!r.ok) return toast(r.msg || "没有可撤销的操作");
    toast(`已撤销：${esc(r.summary || "上一步操作")}`);
    renderSide(); route();
  } catch (e) { toast("撤销失败：" + esc(e)); }
}
function busy(on) { $("#busy").classList.toggle("on", !!on); }

const svg = (d, extra = "") =>
  `<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
     stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;

const IC = {
  overview: svg(`<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/>`),
  library: svg(`<rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="11" r="1.6"/><path d="M4 17l4.5-4.5 3.5 3.5 3-3L20 17"/>`),
  curated: svg(`<path d="M12 3.5l2.6 5.3 5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8L3.5 9.6l5.9-.8z"/>`),
  people: svg(`<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>`),
  places: svg(`<path d="M12 21s-6.5-5.6-6.5-10.5A6.5 6.5 0 0 1 18.5 10.5C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10.4" r="2.4"/>`),
  memories: svg(`<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>`),
  things: svg(`<path d="M20.5 13.3l-7.2 7.2a2 2 0 0 1-2.8 0l-6.5-6.5V3.5h10.5l6 6a2 2 0 0 1 0 2.8z"/><circle cx="7.8" cy="7.8" r="1.3"/>`),
  fav: svg(`<path d="M12 20s-7-4.6-7-9.4A4.1 4.1 0 0 1 12 7a4.1 4.1 0 0 1 7 3.6C19 15.4 12 20 12 20z"/>`),
  video: svg(`<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="M16 11l5-3v8l-5-3z"/>`),
  albums: svg(`<rect x="3" y="5" width="14" height="14" rx="2"/><path d="M7 3h12a2 2 0 0 1 2 2v14"/>`),
  folders: svg(`<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`),
  dup: svg(`<rect x="4" y="4" width="11" height="11" rx="2"/><rect x="9" y="9" width="11" height="11" rx="2"/>`),
  trash: svg(`<path d="M4 7h16M9 7V5h6v2M6.5 7l.9 12h9.2l.9-12M10 11v5M14 11v5"/>`),
  events: svg(`<rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M3 10h18M8 3v4M16 3v4"/>`),
  hidden: svg(`<path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/><path d="M4 4l16 16"/>`),
  trips: svg(`<path d="M2 19l20-7-20-7v5l14 2-14 2z"/><path d="M4 19v3M20 19v3"/>`),
};

const NAV = [
  ["overview", "概览", IC.overview], ["library", "图库", IC.library],
  ["video", "视频", IC.video], ["curated", "精选", IC.curated], ["people", "人物", IC.people],
  ["places", "地点", IC.places], ["memories", "回忆", IC.memories],
  ["things", "事物", IC.things], ["favorites", "收藏", IC.fav],
];
const NAV_EXTRA = [
  ["albums", "相册", IC.albums], ["folders", "文件夹", IC.folders],
  ["trips", "旅行", IC.trips],
  ["duplicates", "重复照片", IC.dup], ["trash", "最近删除", IC.trash],
  ["events", "事件", IC.events], ["hidden", "隐藏", IC.hidden],
];

/* 主题（风格 / 强调色 / 明暗）由 theme.js 统一管理，这里只取数据与入口 */
const { STYLES, ACCENTS, MODES } = window.PATheme;
const applyTheme = window.PATheme.apply;

const S = {
  route: { view: "overview", key: null }, q: "", page: 1, pageSize: 40,
  items: [], total: 0, zoom: 190, sort: "taken_desc", cur: -1,
  layout: localStorage.getItem("pa.layout") || "grid",   // grid | round
  people: [], places: [], curatedIds: [],
  viewItems: [], dayEls: {}, dayCounts: {},
  sel: new Set(), selMode: false, selAnchor: -1, extractIds: null,
  req: 0,                       // 每次换视图自增，晚到的请求不许再改写页面
};

/* ---------------- 工具 ---------------- */
const pad = n => String(n).padStart(2, "0");
function fmtSize(b) {
  return b > 1e9 ? (b / 1e9).toFixed(1) + " GB" :
    b > 1e6 ? (b / 1e6).toFixed(0) + " MB" : Math.round(b / 1e3) + " KB";
}
function fmtTime(t) {
  const d = new Date(t * 1000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fmtDur(s) {
  s = Math.max(0, Math.round(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), ss = s % 60;
  return (h ? h + ":" + pad(m) : String(m)) + ":" + pad(ss);
}
function dayLabel(t) {
  const d = new Date(t * 1000), w = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][d.getDay()];
  const now = new Date();
  const y = d.getFullYear() === now.getFullYear() ? "" : d.getFullYear() + "年";
  return `${y}${d.getMonth() + 1}月${d.getDate()}日 · ${w}`;
}
const dayKey = t => { const d = new Date(t * 1000); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const monthLabel = ym => { const [y, m] = ym.split("-"); return `${y}年 ${Number(m)}月`; };
const ROT = {};                          // 运行期记住刚转过的视频角度，缩略图靠它破缓存
const thumb = (id, size = "s") =>
  `/api/thumb/${id}?size=${size}` + (ROT[id] ? `&r=${ROT[id]}` : "");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------------- 侧栏 ---------------- */
async function renderSide() {
  const [stats, tl] = await Promise.all([api("/api/stats"), api("/api/timeline")]);
  const counts = {
    library: stats.photos, video: stats.videos, curated: stats.picks,
    people: stats.people, places: stats.places, memories: stats.months,
    things: stats.tags, favorites: stats.favorites,
    albums: stats.albums, trash: stats.trash, events: stats.events,
    hidden: stats.hidden, trips: stats.trips,
  };
  const item = ([k, label, icon]) => {
    const on = S.route.view === k || (k === "people" && S.route.view === "person") ||
      (k === "places" && S.route.view === "place") ||
      (k === "albums" && S.route.view === "album") ||
      (k === "trips" && S.route.view === "trip") ||
      (k === "folders" && S.route.view === "folder") ? " active" : "";
    const c = counts[k] != null ? `<span class="side-count">${counts[k]}</span>` : "";
    return `<div class="side-item${on}" data-go="#/${k}">${icon}<span class="t">${label}</span>${c}</div>`;
  };
  $("#nav-main").innerHTML = NAV.map(item).join("");
  $("#nav-extra").innerHTML = NAV_EXTRA.map(item).join("");
  $("#timeline").innerHTML = tl.map(x =>
    `<div class="side-sub" data-go="#/month/${x.ym}"><span>${monthLabel(x.ym)}</span>
     <span class="side-count">${x.c}</span></div>`).join("") ||
    '<div class="side-sub" style="padding-left:10px">暂无</div>';
  $$("[data-go]").forEach(el => el.onclick = () => location.hash = el.dataset.go);
}

/* ---------------- 路由 ---------------- */
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const i = h.indexOf("/");
  const view = i < 0 ? h : h.slice(0, i);
  const key = i < 0 ? null : decodeURIComponent(h.slice(i + 1));
  return { view: view || "overview", key };
}

async function route() {
  S.route = parseHash();
  S.page = 1; S.items = [];
  S.req++;                              // 之前没回来的请求一律作废
  if (S.selMode) selectMode(false);     // 换视图就退出选择，别把上一页的选中带到下一处

  const v = S.route.view;
  // 人物/地点/回忆/事物是卡片页，没有可勾选的磁贴；相册列表、文件夹列表、
  // 重复组、最近删除也各有自己的操作按钮，不给「选择」入口
  $("#btn-select").hidden = ["people", "places", "memories", "things", "albums",
    "folders", "duplicates", "trash", "events", "trips"].includes(v);
  const titles = {
    overview: "概览", library: "图库", video: "视频", curated: "精选", people: "人物",
    places: "地点", memories: "回忆", things: "事物", favorites: "收藏", search: "搜索结果",
    month: monthLabel(S.route.key || "2025-01"), tag: S.route.key || "标签",
    albums: "相册", album: "相册", folders: "文件夹", folder: "文件夹",
    duplicates: "重复照片", trash: "最近删除", events: "事件",
    trips: "旅行", trip: "旅行篇", hidden: "隐藏",
  };
  $("#view-title").textContent = titles[v] || "照片";
  try {
    if (v === "overview") await viewOverview();
    else if (v === "people") await viewPeople();
    else if (v === "places") await viewPlaces();
    else if (v === "memories") await viewMemories();
    else if (v === "things") await viewThings();
    else if (v === "person") await viewPerson(S.route.key);
    else if (v === "place") await viewPlace(S.route.key);
    else if (v === "curated") await viewCurated();
    else if (v === "albums") await viewAlbums();
    else if (v === "album") await viewAlbum(S.route.key);
    else if (v === "folders") await viewFolders();
    else if (v === "folder") await viewFolder(S.route.key);
    else if (v === "duplicates") await viewDuplicates();
    else if (v === "trash") await viewTrash();
    else if (v === "events") await viewEvents();
    else if (v === "trips") await viewTrips();
    else if (v === "trip") await viewTrip(S.route.key);
    else await gridView(v);
  } catch (e) { content.innerHTML = `<div class="empty"><b>出错了</b>${esc(e)}</div>`; }
  markLoadedImages();
  renderSide();
}
window.addEventListener("hashchange", route);

/* ---------------- 通用卡片 ---------------- */
function cardHTML(o) {
  const img = o.cover
    ? `<img loading="lazy" src="${thumb(o.cover)}" alt="">`
    : `<div class="ph">${o.emoji || "—"}</div>`;
  return `<div class="card" data-go="${o.go}">
    <div class="card-img">${img}</div>
    <div class="card-meta"><div class="n1">${esc(o.title)}</div>
    <div class="n2">${esc(o.sub)}</div></div></div>`;
}
function bindGo() { $$("[data-go]").forEach(el => el.onclick = () => location.hash = el.dataset.go); }

/* ---------------- 概览 ---------------- */
async function viewOverview() {
  const d = await api("/api/overview");
  const st = d.stats;
  const hero = d.memories[0];
  content.innerHTML = `<div class="view">
    <div class="stat-row">
      <div class="stat"><div class="n">${st.photos}</div><div class="l">照片与视频</div></div>
      <div class="stat"><div class="n">${st.people}</div><div class="l">人物分组</div></div>
      <div class="stat"><div class="n">${st.places}</div><div class="l">地点</div></div>
      <div class="stat"><div class="n">${fmtSize(st.bytes)}</div><div class="l">图库体积</div></div>
    </div>
    ${hero && hero.cover ? `<div class="hero" data-go="#/${hero.kind === 'place' ? 'place/' + hero.key : 'month/' + hero.key}">
      <img src="${thumb(hero.cover, 'm')}" alt="">
      <div class="ov"><h3>${esc(hero.title)}</h3><p>${esc(hero.subtitle)}</p></div></div>` : ""}
    ${d.people.length ? `<div class="sec-head"><h2>人物</h2>
      <span class="more" data-go="#/people">全部 ${st.people} 人</span></div>
      <div class="row">${d.people.map(p => cardHTML({
        cover: p.cover_photo_id, title: p.name, sub: `${p.photo_count} 张照片`,
        go: `#/person/${p.id}` })).join("")}</div>` : ""}
    ${d.places.length ? `<div class="sec-head"><h2>地点</h2>
      <span class="more" data-go="#/places">全部 ${st.places} 处</span></div>
      <div class="row">${d.places.map(p => cardHTML({
        cover: p.cover_photo_id, title: p.name, sub: `${p.photo_count} 张照片`,
        go: `#/place/${p.id}` })).join("")}</div>` : ""}
    <div class="sec-head"><h2>事物</h2><span class="more" data-go="#/things">全部分类</span></div>
    <div class="chips">${d.tags.map(t =>
      `<span class="chip" data-go="#/tag/${encodeURIComponent(t.tag)}">${esc(t.tag)} ${t.c}</span>`).join("")}</div>
    <div class="sec-head"><h2>最近</h2><span class="more" data-go="#/library">查看图库</span></div>
    <div id="grid"></div>
  </div>`;
  bindGo();
  await appendTiles(`/api/photos?sort=taken_desc&page=1&page_size=24`, true);
}

/* ---------------- 人物 ---------------- */
async function viewPeople() {
  const list = await api("/api/people");
  const groups = list.filter(p => p.kind === "group");
  const solo = list.filter(p => p.kind !== "group" && p.photo_count === 1);
  const multi = list.filter(p => p.kind !== "group" && p.photo_count > 1);
  const cards = arr => arr.map(p => cardHTML({
    cover: p.cover_photo_id, title: p.name, sub: `${p.photo_count} 张照片`,
    go: `#/person/${p.id}` })).join("");
  content.innerHTML = `<div class="view">
    <div class="sec-head"><h2>人物</h2><span class="muted">按出现频率排序 · 可重命名与合并</span></div>
    ${groups.length ? `<h3 class="sub-h">合影</h3><div class="card-grid">${cards(groups)}</div>` : ""}
    ${multi.length ? `<h3 class="sub-h">多人组</h3><div class="card-grid">${cards(multi)}</div>` : ""}
    ${solo.length ? `<h3 class="sub-h">单人照 <span class="muted">${solo.length} 组 · 只有一张</span></h3>
      <div class="card-grid">${cards(solo)}</div>` : ""}
    ${list.length ? "" : `<div class="empty"><b>还没有识别到人物</b>运行「AI 分析」后会自动分组</div>`}
  </div>`;
  bindGo();
}

async function viewPerson(id) {
  const d = await api("/api/people/" + id);
  $("#view-title").textContent = d.person.name;
  content.innerHTML = `<div class="view">
    <div class="sec-head"><h2>${esc(d.person.name)}</h2>
      <span><button class="btn" id="p-rename">重命名</button>
      <button class="btn" id="p-merge" style="margin-left:8px">合并到…</button></span></div>
    <div id="grid"></div></div>`;
  $("#p-rename").onclick = async () => {
    const name = prompt("为此人物命名：", d.person.name);
    if (!name) return;
    await post(`/api/people/${id}/name`, { name });
    toast(`已命名为「${esc(name)}」`); route();
  };
  $("#p-merge").onclick = async () => {
    // 合影组和个人组不互相合并，否则「合影」会被并成某个人的照片集
    const others = (await api("/api/people")).filter(
      p => p.id !== d.person.id && p.kind === d.person.kind);
    if (!others.length) return toast("没有可合并的其他人物");
    const list = others.map((p, i) => `${i + 1}. ${p.name}（${p.photo_count} 张）`).join("\n");
    const pick = prompt(`把「${d.person.name}」合并到：\n${list}\n输入序号：`);
    const t = others[Number(pick) - 1];
    if (!t) return;
    const r = await post("/api/people/merge", { src: d.person.id, dst: t.id });
    toast(`已合并 ${r.merged} 张到「${esc(t.name)}」`);
    location.hash = "#/person/" + t.id;
  };
  S.total = d.items.length;
  renderTiles(d.items);
}

/* ---------------- 地点 ---------------- */
async function viewPlaces() {
  const list = await api("/api/places");
  content.innerHTML = `<div class="view">
    <div class="sec-head"><h2>地点</h2><span class="muted">按 GPS 自动聚合 · 离线城市库</span></div>
    ${list.length ? `<div class="card-grid">${list.map(p => cardHTML({
      cover: p.cover_photo_id, title: p.name,
      sub: `${p.photo_count} 张照片 · ${p.kind === "city" ? "城市" : "区域"}`,
      go: `#/place/${p.id}` })).join("")}</div>`
      : `<div class="empty"><b>没有带位置信息的照片</b>相机的 GPS 信息会自动归类</div>`}
  </div>`;
  bindGo();
}

async function viewPlace(id) {
  const d = await api("/api/places/" + id);
  $("#view-title").textContent = d.place.name;
  content.innerHTML = `<div class="view">
    <div class="sec-head"><h2>${esc(d.place.name)}</h2>
      <span class="muted">${d.items.length} 张照片 ·
      <a class="v-link" target="_blank"
        href="https://uri.amap.com/marker?position=${d.place.lon},${d.place.lat}">在地图中查看</a></span></div>
    <div id="grid"></div></div>`;
  S.total = d.items.length;
  renderTiles(d.items);
}

/* ---------------- 回忆 ---------------- */
async function viewMemories() {
  const list = await api("/api/memories");
  const months = list.filter(x => x.kind === "month").slice(0, 6);
  const places = list.filter(x => x.kind === "place");
  content.innerHTML = `<div class="view">
    ${months.length ? `<div class="sec-head"><h2>月度回忆</h2><span class="muted">按时间自动生成</span></div>
      <div class="row">${months.map(m => cardHTML({ cover: m.cover, title: m.title,
        sub: m.subtitle, go: `#/month/${m.key}` })).join("")}</div>` : ""}
    ${places.length ? `<div class="sec-head"><h2>地点回忆</h2><span class="muted">去过的地方</span></div>
      <div class="row">${places.map(m => cardHTML({ cover: m.cover, title: m.title,
        sub: m.subtitle, go: `#/place/${m.key}` })).join("")}</div>` : ""}
    ${!list.length ? `<div class="empty"><b>暂无回忆</b>导入照片后自动生成</div>` : ""}
  </div>`;
  bindGo();
}

/* ---------------- 事物 ---------------- */
async function viewThings() {
  const list = await api("/api/things");
  content.innerHTML = `<div class="view">
    <div class="sec-head"><h2>事物分类</h2><span class="muted">按内容自动打标</span></div>
    ${list.length ? `<div class="card-grid">${list.map(t => cardHTML({
      cover: t.cover, title: t.name, sub: `${t.count} 张照片`,
      go: `#/tag/${encodeURIComponent(t.name)}` })).join("")}</div>`
      : `<div class="empty"><b>还没有分类</b>运行「AI 分析」开始打标</div>`}
  </div>`;
  bindGo();
}

/* ---------------- 精选 ---------------- */
async function viewCurated() {
  const d = await api("/api/curated");
  if (!d.items.length) {
    content.innerHTML = `<div class="empty"><b>暂无精选</b>运行「AI 分析」后自动挑选最佳照片</div>`;
    return;
  }
  const hero = d.hero;
  content.innerHTML = `<div class="view">
    <div class="hero" data-id="${hero.id}"><img src="${thumb(hero.id, 'm')}" alt="">
      <div class="ov"><h3>今日精选</h3><p>${esc(hero.reason)} · 画质评分 ${Math.round(hero.quality || 0)}</p></div></div>
    <div class="sec-head"><h2>共 ${d.total} 张精选</h2>
      <span class="muted">连拍最佳 · 画质优秀 · 你的收藏</span></div>
    <div id="grid"></div></div>`;
  content.querySelector(".hero").onclick = () => openViewer(d.items, 0);
  S.curatedIds = d.items.map(x => x.id);
  S.total = d.items.length;
  renderTiles(d.items.slice(1), { showReason: true });
}

/* ---------------- 相册 ---------------- */
async function viewAlbums() {
  const list = await api("/api/albums");
  content.innerHTML = `<div class="view">
    <div class="view-tools"><span class="hint">相册只记录成员关系，照片仍只存一份</span>
      <span class="grow"></span><button class="btn primary" id="al-new">新建相册</button></div>
    ${list.length ? `<div class="card-grid">${list.map(a => cardHTML({
      cover: a.cover_photo_id, title: a.name, sub: `${a.c} 张照片`, go: `#/album/${a.id}`,
    })).join("")}</div>` : `<div class="empty"><b>还没有相册</b>新建一个，再把照片批量加进来</div>`}
  </div>`;
  $("#al-new").onclick = async () => {
    const name = (prompt("相册名称：") || "").trim();
    if (!name) return;
    try {
      const r = await post("/api/albums", { name });
      location.hash = `#/album/${r.id}`;
      renderSide();
    } catch (e) { toast("新建失败：" + esc(e)); }
  };
  bindGo();
}

async function viewAlbum(id) {
  const d = await api(`/api/albums/${id}`);
  content.innerHTML = `<div class="view">
    <div class="view-head">
      <div><h2>${esc(d.album.name)}</h2><p>${d.items.length} 张照片</p></div>
      <span class="grow"></span>
      <button class="btn" id="al-rename">重命名</button>
      <button class="btn danger" id="al-del">删除相册</button>
    </div>
    <div id="grid"></div></div>`;
  renderTiles(d.items, { group: true });
  $("#al-rename").onclick = async () => {
    const name = (prompt("新的相册名：", d.album.name) || "").trim();
    if (!name || name === d.album.name) return;
    try { await post(`/api/albums/${id}/rename`, { name }); route(); renderSide(); }
    catch (e) { toast("重命名失败：" + esc(e)); }
  };
  $("#al-del").onclick = async () => {
    if (!confirm(`删除相册「${d.album.name}」？照片本身不会被删除。`)) return;
    await fetch(`/api/albums/${id}`, { method: "DELETE" });
    toast("相册已删除，照片仍在图库");
    location.hash = "#/albums";
    renderSide();
  };
}

/* ---------------- 文件夹 ---------------- */
async function viewFolders() {
  const tree = await api("/api/folders?tree=1");
  const row = n => `<div class="folder-row" data-go="#/folder/${encodeURIComponent(n.path)}">
      <span class="fi">${IC.folders}</span>
      <span class="t">${esc(n.name)}</span>
      <span class="side-count">${n.count} 张 · ${fmtSize(n.size)}</span>
    </div>`;
  content.innerHTML = `<div class="view">
    <div class="view-tools"><span class="hint">按硬盘真实目录浏览；这里只读索引，不移动任何文件</span></div>
    <div class="folder-list">${tree.length ? tree.map(row).join("") : `<div class="empty"><b>还没有导入照片</b></div>`}</div>
  </div>`;
  bindGo();
}

async function viewFolder(path) {
  const d = await api("/api/folder?path=" + encodeURIComponent(path));
  const parts = path.split("\\").filter(Boolean);
  let acc = "";
  const crumbs = parts.map((p, i) => {
    acc = i === 0 ? p : acc + "\\" + p;
    return `<a class="crumb" href="#/folder/${encodeURIComponent(acc)}">${esc(p)}</a>`;
  }).join('<span class="cr-sep">›</span>');
  content.innerHTML = `<div class="view">
    <div class="crumb-row"><a class="crumb" href="#/folders">文件夹</a>
      <span class="cr-sep">›</span>${crumbs}</div>
    ${d.children.length ? `<div class="subfolders">${d.children.map(c =>
      `<a class="chip" href="#/folder/${encodeURIComponent(c.dir)}">${esc(c.dir.split("\\").pop())}
        <em>${c.c}</em></a>`).join("")}</div>` : ""}
    <div class="view-tools"><span class="hint">${d.items.length} 张照片 · ${esc(path)}</span></div>
    <div id="grid"></div></div>`;
  renderTiles(d.items, { group: true });
}

/* ---------------- 重复照片 ---------------- */
async function viewDuplicates() {
  const groups = await api("/api/duplicates");
  const waste = groups.reduce((a, g) => a + g.bytes, 0);
  content.innerHTML = `<div class="view">
    <div class="view-tools"><span class="hint">${groups.length} 组重复 · 共占 ${fmtSize(waste)}。
      保留每组画质最高的一张，其余可以一次性移入最近删除。</span></div>
    ${groups.length ? groups.map(g => `<div class="dupe-group">
      <div class="dg-head"><b>${g.count} 张相同内容</b>
        <span class="side-count">${fmtSize(g.bytes)}</span><span class="grow"></span>
        <button class="btn" data-dupe="${g.hash}">保留最佳，其余进最近删除</button></div>
      <div class="dg-items">${g.items.map(it => `<div class="dg-item${it.id === g.keep ? " best" : ""}">
        <img loading="lazy" src="${thumb(it.id)}" alt="">
        <div class="dg-meta"><b>${esc(it.name)}</b>
          <span>${fmtSize(it.size)} · ${it.width || "?"}×${it.height || "?"}</span>
          <span class="dg-path" title="${esc(it.dir)}">${esc(it.dir)}</span>
          ${it.id === g.keep ? '<em>保留</em>' : ""}</div></div>`).join("")}</div>
    </div>`).join("") : `<div class="empty"><b>没有发现重复照片</b>内容完全一致的照片才会出现在这里</div>`}
  </div>`;
  $$("[data-dupe]").forEach(b => b.onclick = async () => {
    const g = groups.find(x => x.hash === b.dataset.dupe);
    if (!g) return;
    const ids = g.items.filter(x => x.id !== g.keep).map(x => x.id);
    try {
      const r = await post("/api/photos/batch/delete", { ids, mode: "trash" });
      toastUndo(`已把 ${r.count} 张重复照片移入最近删除`);
      route(); renderSide();
    } catch (e) { toast("操作失败：" + esc(e)); }
  });
}

/* ---------------- 最近删除 ---------------- */
async function viewTrash() {
  const d = await api("/api/trash");
  content.innerHTML = `<div class="view">
    <div class="view-tools"><span class="hint">最近删除保留 ${d.days} 天。清空会真正删除文件，不可恢复。</span>
      <span class="grow"></span>
      <button class="btn danger" id="tr-empty" ${d.items.length ? "" : "disabled"}>清空最近删除</button></div>
    ${d.items.length ? `<div class="trash-list">${d.items.map(t => `<div class="trash-item">
      <img loading="lazy" src="${thumb(t.photo_id)}" alt="">
      <div class="ti-meta"><b>${esc(t.name || "未命名")}</b>
        <span>${fmtTime(t.deleted_at)} · ${t.kind === "trash" ? "文件在最近删除" : "仅移除索引"}</span>
        <span class="dg-path" title="${esc(t.path || "")}">${esc(t.path || "")}</span></div>
      <span class="side-count">${t.size ? fmtSize(t.size) : ""}</span>
      <button class="btn" data-restore="${t.id}">恢复</button>
      <button class="btn danger" data-purger="${t.id}">彻底删除</button>
    </div>`).join("")}</div>` : `<div class="empty"><b>最近删除是空的</b>删除照片时会先放到这里</div>`}
  </div>`;
  $$("[data-restore]").forEach(b => b.onclick = async () => {
    try {
      await post(`/api/trash/${b.dataset.restore}/restore`);
      toast("已恢复");
      route(); renderSide();
    } catch (e) { toast("恢复失败：" + esc(e)); }
  });
  $$("[data-purger]").forEach(b => b.onclick = async () => {
    if (!confirm("彻底删除这个文件？此操作不可恢复。")) return;
    try {
      await post(`/api/trash/${b.dataset.purger}/purge`);
      toast("已彻底删除");
      route(); renderSide();
    } catch (e) { toast("删除失败：" + esc(e)); }
  });
  const em = $("#tr-empty");
  if (em) em.onclick = async () => {
    if (!confirm("清空最近删除会真正删除其中所有文件，确定继续？")) return;
    try {
      const r = await post("/api/trash/empty");
      toast(`已清空最近删除（${r.files} 个文件）`);
      route(); renderSide();
    } catch (e) { toast("清空失败：" + esc(e)); }
  };
}

/* ---------------- 事件 ---------------- */
async function viewEvents() {
  const list = await api("/api/events?limit=48");
  content.innerHTML = `<div class="view">
    <div class="view-tools"><span class="hint">同一天、照片数量足够多的日子自动聚成事件</span></div>
    ${list.length ? `<div class="card-grid">${list.map(e => cardHTML({
      cover: e.cover, title: `${e.date}${e.place ? " · " + e.place : ""}`,
      sub: `${e.count} 张照片`, go: `#/month/${e.date.slice(0, 7)}`,
    })).join("")}</div>` : `<div class="empty"><b>还没有可聚合的事件</b></div>`}
  </div>`;
  bindGo();
}

/* ---------------- 旅行篇 ---------------- */
async function viewTrips() {
  const list = await api("/api/trips");
  content.innerHTML = `<div class="view">
    <div class="view-tools"><span class="hint">按 GPS 与拍摄日期自动识别：连续几天在外、照片达到 8 张以上</span></div>
    ${list.length ? `<div class="card-grid">${list.map(t => cardHTML({
      cover: t.cover, title: t.title, sub: `${t.count} 张 · ${t.days} 天`,
      go: `#/trip/${t.key}` })).join("")}</div>`
    : `<div class="empty"><b>还没有识别到旅行</b>带 GPS 的照片连续拍几天，就会自动成篇</div>`}
  </div>`;
  bindGo();
}

async function viewTrip(key) {
  const d = await api("/api/trips/" + encodeURIComponent(key));
  const t = d.trip;
  content.innerHTML = `<div class="view">
    <div class="view-head">
      <div><h2>${esc(t.title)}</h2><p>${t.count} 张照片 · ${t.days} 天 · 位置 ${t.lat}, ${t.lon}</p></div>
      <span class="grow"></span>
      <a class="btn" target="_blank"
        href="https://uri.amap.com/marker?position=${t.lon},${t.lat}">在地图中查看</a>
    </div>
    <div class="sec-head"><h2>本篇精选</h2><span class="muted">收藏与高画质优先排在前面</span></div>
    <div id="grid"></div></div>`;
  renderTiles(d.items, { group: true });
}

/* ---------------- 网格 / 环形视图 ---------------- */
async function gridView(v) {
  if (S.layout === "round") {
    // 先把空盘和转圈放上屏，照片回来再填 —— 切布局不该先卡住等接口
    content.innerHTML = `<div class="view"><div id="grid" class="orb-wrap">
      <div class="orb-load"><span class="spinner"></span>正在载入照片…</div></div></div>`;
    const grid = $("#grid");
    const my = S.req;
    const url = new URL(buildQuery(v, 1), location.origin);
    url.searchParams.set("page_size", "200");
    // 先让占位转圈上屏，再发请求。这里不能用 requestAnimationFrame：
    // 窗口被遮挡或最小化时 rAF 会被浏览器暂停，切布局就会永远停在这个圈上。
    await new Promise(r => setTimeout(r, 0));
    const d = await api(url.pathname + url.search);
    if (my !== S.req || !grid.isConnected) return;      // 已经切走了，别覆盖新页面
    if (!d.items.length) {
      grid.innerHTML = `<div class="empty"><b>这里还没有照片</b>
        点右上角「导入」选择照片文件夹</div>`;
      return;
    }
    S.items = d.items; S.viewItems = d.items; S.total = d.total; S.page = d.page;
    const loadPage = async page => {
      if (my !== S.req) return [];
      const u = new URL(buildQuery(v, 1), location.origin);
      u.searchParams.set("page_size", "200");
      u.searchParams.set("page", String(page));
      const r = await api(u.pathname + u.search);
      S.total = r.total;
      return r.items;
    };
    OrbLayout.mount(grid, {
      items: d.items, total: d.total, pageSize: 200, loadPage,
      onOpen: i => {
        const it = OrbLayout.items()[i];
        if (!it) return;
        if (S.selMode) {
          S.sel.has(it.id) ? S.sel.delete(it.id) : S.sel.add(it.id);
          syncSel();
          return;
        }
        openViewer(OrbLayout.items(), i);
      },
    });
    markLoadedImages();
    return;
  }
  content.innerHTML = `<div class="view"><div id="grid"></div>
    <div id="sentinel" style="height:40px"></div></div>`;
  await appendTiles(buildQuery(v, 1), true);
  observeMore(v);
  markLoadedImages();
}

function buildQuery(v, page) {
  const p = new URLSearchParams({ sort: S.sort, page, page_size: S.pageSize });
  if (v === "favorites") p.set("favorite", "1");
  else if (v === "video") p.set("kind", "video");
  else if (v === "month") p.set("month", S.route.key);
  else if (v === "tag") p.set("tag", S.route.key);
  else if (v === "folder") p.set("dir", S.route.key);
  else if (v === "search") p.set("q", S.route.key);
  else if (v === "hidden") p.set("hidden", "1");
  return "/api/photos?" + p;
}

/* 当前页面对应的筛选条件：供「整理到文件夹」复用同一批照片 */
function currentFilter() {
  const v = S.route.view, k = S.route.key;
  if (v === "person") return { label: "当前人物", f: { person_id: +k } };
  if (v === "place") return { label: "当前地点", f: { place_id: +k } };
  if (v === "month") return { label: "当前月份", f: { month: k } };
  if (v === "folder") return { label: "当前文件夹", f: { dir: k } };
  if (v === "tag") return { label: `标签「${k}」`, f: { tag: k } };
  if (v === "search") return { label: `搜索「${k}」`, f: { q: k } };
  if (v === "favorites") return { label: "收藏", f: { favorite: 1 } };
  if (v === "video") return { label: "视频", f: { kind: "video" } };
  if (v === "hidden") return { label: "隐藏", f: { hidden: 1 } };
  if (v === "curated") return { label: "精选", f: { ids: S.curatedIds } };
  return { label: v === "library" ? "整个图库" : "当前视图", f: {} };
}

async function appendTiles(url, reset) {
  const grid = $("#grid");
  if (!grid) return;
  const my = S.req;
  if (reset) {
    grid.innerHTML = Array.from({ length: 12 }, () => '<div class="sk"></div>').join("");
  }
  const d = await api(url);
  if (my !== S.req || !grid.isConnected) return;       // 请求回来时页面已经换了
  S.total = d.total; S.page = d.page;
  if (reset) {
    S.items = []; S.dayEls = {}; S.dayCounts = {};
    grid.innerHTML = "";          // 清掉骨架屏
  }
  const start = S.items.length;
  const merged = S.items.concat(d.items);
  S.items = merged; S.viewItems = merged;
  if (!d.items.length && !merged.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><b>这里还没有照片</b>
      点右上角「导入」选择照片文件夹</div>`;
  } else {
    appendChunk(grid, d.items, start, { group: true });
    bindTiles(grid);
  }
  if (d.semantic) toast("已启用语义搜索");
  if (S.selMode) syncSel();
  return d;
}

/* 增量追加一批照片：只插入新 DOM，不重建已渲染的瓷砖 */
function appendChunk(grid, chunk, start, opt) {
  let html = "", lastDay = null;
  const touched = new Set();
  chunk.forEach((it, idx) => {
    if (opt.group) {
      const k = dayKey(it.taken_at || 0);
      S.dayCounts[k] = (S.dayCounts[k] || 0) + 1;
      touched.add(k);
      if (k !== lastDay && !S.dayEls[k]) {
        html += `<div class="day-head" data-day="${k}"
          data-place="${esc(it.place || "")}">${dayLabel(it.taken_at || 0)}
          <span class="hd-c"></span></div>`;
      }
      lastDay = k;
    }
    html += tileHTML(it, start + idx, opt);
  });
  grid.insertAdjacentHTML("beforeend", html);
  touched.forEach(k => {
    if (!S.dayEls[k]) S.dayEls[k] = grid.querySelector(`.day-head[data-day="${k}"]`);
    const el = S.dayEls[k];
    if (el) el.querySelector(".hd-c").textContent =
      `${S.dayCounts[k] || 0} 张${el.dataset.place ? " · " + el.dataset.place : ""}`;
  });
}

function tileHTML(it, i, opt = {}) {
  // 右下角那枚角标：视频给时长，照片给画质/推荐理由。位置一样，同一时刻只显示一个。
  const isVid = it.kind === "video";
  const badge = isVid ? (it.duration ? `<span class="bd">${fmtDur(it.duration)}</span>` : "")
    : (opt.showReason && it.reason ? `<span class="bd">${esc(it.reason)}</span>`
      : (it.quality >= 68 ? `<span class="bd">画质 ${Math.round(it.quality)}</span>` : ""));
  return `<div class="tile" data-i="${i}">
    <img loading="lazy" src="${thumb(it.id)}" alt="">
    ${isVid ? `<div class="vid">${IC.video}</div>` : ""}
    ${it.is_live ? `<span class="live">实况</span>` : ""}
    ${it.is_favorite ? `<span class="fav">♥</span>` : ""}${badge}
    <span class="pick"></span></div>`;
}

function bindTiles(root) {
  root.querySelectorAll(".tile:not([data-bound])").forEach(el => {
    el.dataset.bound = "1";
    el.onclick = e => {
      if (Date.now() < suppressClickUntil) return;   // 刚拖完框选，别把落点那张取消掉
      // 选择态下点磁贴只切换勾选，绝不打开查看器
      if (S.selMode) { tileToggle(Number(el.dataset.i), e); return; }
      openViewer(S.viewItems, Number(el.dataset.i));
    };
  });
}

/* 一次性渲染（人物 / 地点 / 精选等数据量小的页面） */
function renderTiles(items, opt = {}) {
  const grid = $("#grid");
  if (!grid) return;
  if (S.layout === "round") {
    grid.classList.add("orb-wrap");
    S.viewItems = items;
    OrbLayout.mount(grid, { items, total: items.length,
      onOpen: i => {
        const it = items[i];
        if (!it) return;
        if (S.selMode) {
          S.sel.has(it.id) ? S.sel.delete(it.id) : S.sel.add(it.id);
          syncSel();
          return;
        }
        openViewer(items, i);
      } });
    return;
  }
  grid.classList.remove("orb-wrap");
  if (!items.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><b>这里还没有照片</b>
      点右上角「导入」选择照片文件夹</div>`;
    return;
  }
  S.viewItems = items; S.dayEls = {}; S.dayCounts = {};
  const counts = {};
  if (opt.group) items.forEach(it => {
    const k = dayKey(it.taken_at || 0); counts[k] = (counts[k] || 0) + 1;
  });
  let html = "", lastDay = null;
  items.forEach((it, i) => {
    if (opt.group) {
      const k = dayKey(it.taken_at || 0);
      if (k !== lastDay) {
        lastDay = k;
        html += `<div class="day-head">${dayLabel(it.taken_at || 0)}
          <span>${counts[k]} 张${it.place ? " · " + esc(it.place) : ""}</span></div>`;
      }
    }
    html += tileHTML(it, i, opt);
  });
  grid.innerHTML = html;
  bindTiles(grid);
  if (S.selMode) syncSel();
}

/* ---------------- 多选与批量操作 ---------------- */
/* S.sel 存的是照片 id（不是下标）：翻页追加、删掉中间几张都不会选错对象 */
const selIds = () => [...S.sel];

function selectMode(on) {
  S.selMode = !!on;
  if (!S.selMode) { S.sel.clear(); S.selAnchor = -1; }
  document.body.classList.toggle("selmode", S.selMode);
  const b = $("#btn-select");
  b.classList.toggle("on", S.selMode);
  b.textContent = S.selMode ? "完成" : "选择";
  if (!S.selMode) { const m = $("#marquee"); if (m) m.remove(); }
  syncSel();
}

/* 只改 class 与计数，不重绘网格 —— 勾选时磁贴不该闪一下 */
function syncSel() {
  const n = S.sel.size;
  $("#sb-count").textContent = n ? `已选 ${n} 张` : "未选择照片";
  $$("#selbar .sb-btn").forEach(b => {
    if (b.id !== "sb-all" && b.id !== "sb-done") b.disabled = !n;
  });
  $$("#grid .tile").forEach(el => {
    const it = S.viewItems[Number(el.dataset.i)];
    el.classList.toggle("sel", !!it && S.sel.has(it.id));
  });
  // 表盘视图里的照片也要跟着显示选中状态
  const orbItems = window.OrbLayout ? OrbLayout.items() : [];
  $$("#grid .orb-node").forEach(el => {
    const it = orbItems[Number(el.dataset.i)];
    el.classList.toggle("sel", !!it && S.sel.has(it.id));
  });
}

function tileToggle(i, e) {
  const it = S.viewItems[i];
  if (!it) return;
  if (e && e.shiftKey && S.selAnchor >= 0) {
    // Shift 连选：以锚点到当前点为区间，区间内统一设为"选中"或"取消"
    const a = Math.min(S.selAnchor, i), b = Math.max(S.selAnchor, i);
    const want = !S.sel.has(it.id);
    for (let k = a; k <= b; k++) {
      const x = S.viewItems[k];
      if (!x) continue;
      if (want) S.sel.add(x.id); else S.sel.delete(x.id);
    }
  } else {
    if (S.sel.has(it.id)) S.sel.delete(it.id); else S.sel.add(it.id);
    S.selAnchor = i;
  }
  syncSel();
}

/* 全选当前视图的全部匹配项（不只是已经滚出来的那几屏） */
async function selectAll() {
  try {
    const v = S.route.view;
    if (v === "overview" || v === "curated") {
      S.viewItems.forEach(it => S.sel.add(it.id));
    } else {
      const p = new URLSearchParams({ sort: S.sort });
      const { f } = currentFilter();
      for (const [k, val] of Object.entries(f)) {
        if (val != null && val !== "") p.set(k, val);
      }
      const r = await api("/api/photos/ids?" + p);
      (r.ids || []).forEach(id => S.sel.add(id));
    }
    syncSel();
    toast(`已选中 ${S.sel.size} 张`, 1500);
  } catch (e) { toast("全选失败：" + esc(e)); }
}

/* 拖拽框选：选择模式下可以从任意位置起手（包括照片上），拖出一个矩形批量选中 */
let boxSel = null;
let suppressClickUntil = 0;
function boxStart(e) {
  if (!S.selMode || e.button !== 0) return;
  const grid = $("#grid");
  if (!grid || !grid.contains(e.target)) return;
  if (grid.classList.contains("orb-wrap")) return;   // 表盘视图拖动是浏览照片，不是框选
  if (e.target.closest(".day-head")) return;
  boxSel = { x: e.clientX, y: e.clientY, base: new Set(S.sel), moved: false, el: null };
  window.addEventListener("pointermove", boxMove);
  window.addEventListener("pointerup", boxEnd);
}
function boxMove(e) {
  if (!boxSel) return;
  const dx = e.clientX - boxSel.x, dy = e.clientY - boxSel.y;
  if (!boxSel.moved && Math.hypot(dx, dy) < 6) return;
  boxSel.moved = true;
  if (!boxSel.el) {
    boxSel.el = document.createElement("div");
    boxSel.el.id = "marquee";
    document.body.appendChild(boxSel.el);
  }
  const x = Math.min(boxSel.x, e.clientX), y = Math.min(boxSel.y, e.clientY);
  const w = Math.abs(dx), h = Math.abs(dy);
  Object.assign(boxSel.el.style,
    { display: "block", left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
  S.sel = new Set(boxSel.base);
  $$("#grid .tile").forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.left < x + w && r.right > x && r.top < y + h && r.bottom > y) {
      const it = S.viewItems[Number(el.dataset.i)];
      if (it) S.sel.add(it.id);
    }
  });
  syncSel();
}
function boxEnd() {
  window.removeEventListener("pointermove", boxMove);
  window.removeEventListener("pointerup", boxEnd);
  if (boxSel && boxSel.el) boxSel.el.remove();
  // 拖出过矩形就屏蔽随后的 click，避免手指抬起时又把起手那张取消掉
  if (boxSel && boxSel.moved) suppressClickUntil = Date.now() + 250;
  boxSel = null;
  syncSel();
}

async function batchFav(value) {
  const ids = selIds();
  if (!ids.length) return;
  try {
    const r = await post("/api/photos/batch/favorite", { ids, value });
    S.viewItems.forEach(it => { if (S.sel.has(it.id)) it.is_favorite = value ? 1 : 0; });
    $$("#grid .tile").forEach(el => {
      const it = S.viewItems[Number(el.dataset.i)];
      if (!it || !S.sel.has(it.id)) return;
      const f = el.querySelector(".fav");
      if (value && !f) {
        const s = document.createElement("span");
        s.className = "fav"; s.textContent = "♥"; el.appendChild(s);
      } else if (!value && f) f.remove();
    });
    renderSide();
    toast(value ? `已收藏 ${r.count} 张` : `已取消收藏 ${r.count} 张`, 2000);
  } catch (e) { toast("操作失败：" + esc(e)); }
}

function askBatchDelete() {
  const n = S.sel.size;
  if (!n) return;
  $("#dlg-bdel-sub").textContent = `已选 ${n} 张照片。默认先放进最近删除，30 天内都能恢复。`;
  $("#dlg-bdel").classList.add("open");
}
/* 删除方式单选：选中项高亮，danger 项给红色描边提醒 */
$$(".del-modes").forEach(box => box.addEventListener("change", () => {
  box.querySelectorAll(".del-mode").forEach(l =>
    l.classList.toggle("on", l.querySelector("input").checked));
}));

function observeMore(v) {
  const sen = $("#sentinel");
  if (!sen) return;
  const ob = new IntersectionObserver(async entries => {
    if (!entries[0].isIntersecting) return;
    if (S.items.length >= S.total) { ob.disconnect(); sen.remove(); return; }
    ob.disconnect();
    sen.remove();
    const nextPage = S.page + 1;
    const marker = document.createElement("div");
    marker.id = "sentinel"; marker.style.height = "40px";
    content.appendChild(marker);
    await appendTiles(buildQuery(v, nextPage), false);
    observeMore(v);
  }, { root: $("#content"), rootMargin: "400px" });
  ob.observe(sen);
}

/* ---------------- 查看器 ---------------- */
let V = { list: [], i: -1 };
/* vSeq 是切图序号：每次换图 +1，所有在途的图片加载与元数据请求都要核对它，
   不匹配就直接丢弃 —— 连按方向键时上一张的响应绝不会盖到当前这张上。 */
let vSeq = 0;
/* 当前已显示的画质档：1 = s 缩略图，2 = m 缩略图，3 = 原图。
   低档姗姗来迟时直接跳过，避免"已经看到原图又被缩略图糊回去"。 */
let vShownLevel = 0;
/* 原图升级定时器：连按方向键时不停手就不要去读几十兆的原图，
   否则机械硬盘上三路请求互相抢磁头，反而把翻页拖慢。停手 160ms 后再升。 */
let vFullTimer = 0;
/* 邻居 m 缩略图的延迟预取定时器，同上：连翻时不预取 */
let vPreTimer = 0;
const vImgA = $("#v-img"), vImgB = $("#v-img2");
let vFront = vImgA;                       // 两张 img 交替当前景，换图时交叉淡入

function openViewer(list, i) {
  V = { list, i };
  $("#viewer").classList.add("open");
  document.body.style.overflow = "hidden";
  showPhoto(i);
}
function closeViewer() {
  edExit();                                // 关窗前先退出编辑态，别把面板残留到下次
  vSeq++;                                  // 作废所有在途请求
  clearTimeout(vFullTimer);                // 别让已经排队的原图请求在关窗后又冒出来
  clearTimeout(vPreTimer);
  $("#viewer").classList.remove("open", "info-on", "chrome-off");
  $("#v-info-btn").classList.remove("on");
  document.body.style.overflow = "";
  vShowVideo(null);    // 松开视频解码器，顺手把海报也撤掉
  stopPlay();          // 关窗即停幻灯片，免得定时器还在后台偷偷翻页
}
function step(d) {
  if (!V.list.length) return;
  V.i = (V.i + d + V.list.length) % V.list.length;
  showPhoto(V.i);
}

/* 空格键幻灯片：每 3 秒翻一张，循环播放，关窗自动停 */
let playTimer = null;
function stopPlay() {
  if (!playTimer) return false;
  clearInterval(playTimer); playTimer = null;
  return true;
}
function togglePlay() {
  if (!V.list.length) return;
  if (stopPlay()) return toast("幻灯片已暂停");
  playTimer = setInterval(() => step(1), 3000);
  toast("幻灯片播放中（再按空格暂停）");
}

/* 舞台同时容纳一张图和一段视频，同一时刻只亮一个。
   切到视频要把图片那套缩放/位移清掉；切走要把解码器松开，否则连翻十几段
   片子会在内存里越堆越多。 */
const vVid = $("#v-vid");
function vShowVideo(it) {
  const on = !!it && it.kind === "video";
  vStage.classList.toggle("video-on", on);
  if (!on) {
    vVid.pause();
    vVid.removeAttribute("src");     // 清 src 才会真正释放解码器
    vVid.removeAttribute("poster");
    vVid.dataset.id = "";
    vVid.style.transform = "";
    vVid.classList.remove("rot90");
    return;
  }
  const deg = Number(it.rotate) || 0;
  vVid.style.transform = deg ? `rotate(${deg}deg)` : "";
  vVid.classList.toggle("rot90", deg === 90 || deg === 270);
  // 同一段片子就别重设 src 了，否则切走再切回来会从头开始
  if (vVid.dataset.id !== String(it.id)) {
    vVid.dataset.id = it.id;
    vVid.poster = thumb(it.id, "m");      // 中等缩略图当封面，秒出画面
    vVid.src = "/api/image/" + it.id;     // FileResponse 已支持 Range，进度条能拖
  }
}

/* 已加载过的图片对象做小 LRU 缓存：预加载与快速回翻都直接命中，不重复解码。
   上限 24 条是有意的 —— 只覆盖前后两张的预取窗口，内存不会随翻页线性增长。 */
const VCACHE = new Map(), VCACHE_MAX = 24;
function vLoad(id, size) {
  const key = id + ":" + (size || "full");
  let im = VCACHE.get(key);
  if (im) { VCACHE.delete(key); VCACHE.set(key, im); return im; }
  im = new Image();
  im.decoding = "async";
  im.src = size ? thumb(id, size) : "/api/image/" + id;
  VCACHE.set(key, im);
  while (VCACHE.size > VCACHE_MAX) VCACHE.delete(VCACHE.keys().next().value);
  return im;
}

/* 双图层交叉淡入：新图在背后那张解好再交换，中间不会闪黑。
   level 越大越清晰，迟到的低清结果不许把已经显示的高清盖回去。 */
function vSwap(id, size, seq, level) {
  const im = vLoad(id, size);
  const apply = () => {
    if (seq !== vSeq || level < vShownLevel) return;
    const back = vFront === vImgA ? vImgB : vImgA;
    if (back.getAttribute("src") !== im.src) back.src = im.src;
    back.classList.add("show");
    vFront.classList.remove("show");
    vFront = back;
    vShownLevel = level;
  };
  if (im.complete && im.naturalWidth) apply();
  else im.addEventListener("load", apply, { once: true });
}

/* 预取前后各两张：s 立刻取（每张几十 KB，下一张首帧就有画面）。
   m 更大、解码更重，放到「停手 180ms」之后再取 —— 连按方向键时不去抢磁盘，
   也不会产生一堆被浏览器中断的请求（控制台里那串 ERR_ABORTED 就是它）。 */
function vPreloadAround(i) {
  const n = V.list.length;
  for (const d of [-2, -1, 1, 2]) {
    const it = V.list[(i + d + n) % n];
    if (it && it.kind !== "video") vLoad(it.id, "s");
  }
  clearTimeout(vPreTimer);
  vPreTimer = setTimeout(() => {
    if (i !== V.i) return;
    for (const d of [-1, 1]) {
      const it = V.list[(i + d + n) % n];
      if (it && it.kind !== "video") vLoad(it.id, "m");
    }
  }, 180);
}

function showPhoto(i) {
  const it = V.list[i];
  if (!it) return;
  if (ED.on) edExit();
  const seq = ++vSeq;
  vShownLevel = 0;
  vReset();   // 换图先回到 1×，否则上一张的缩放和位移会被带过来
  const isVid = it.kind === "video";
  vShowVideo(isVid ? it : null);
  if (!isVid) {
    // s 一定在磁盘上、浏览器也基本缓存过 —— 先秒上屏，再逐级升级到 m 与原图
    vSwap(it.id, "s", seq, 1);
    vSwap(it.id, "m", seq, 2);
    clearTimeout(vFullTimer);
    vFullTimer = setTimeout(() => { if (seq === vSeq) vSwap(it.id, null, seq, 3); }, 160);
  }
  $("#v-name").textContent = it.name || "";
  $("#v-info-name").textContent = it.name || "";
  $("#v-ext").hidden = !isVid;    // 「系统播放器」这枚按钮只有视频才给
  $("#v-edit").hidden = isVid;    // 视频不参与图片编辑
  $("#v-rotl").hidden = !isVid;   // 视频用的是「只改显示角度」的旋转，不动原文件
  $("#v-rotr").hidden = !isVid;
  $("#v-live").hidden = !it.is_live;
  $("#v-hide").title = it.hidden ? "取消隐藏 (H)" : "隐藏这张 (H)";
  $("#v-fav").classList.toggle("on", !!it.is_favorite);
  // 列表行里已经有完整元数据，先把信息面板画出来；直方图等接口回来再补
  renderInfo(it, null);
  vPreloadAround(i);
  const meta = api("/api/photo/" + it.id);
  meta.then(d => {
    if (seq !== vSeq) return;      // 已经翻走，过期响应直接丢
    $("#v-name").textContent = d.name || it.name || "";
    $("#v-info-name").textContent = d.name || it.name || "";
    $("#v-fav").classList.toggle("on", !!d.is_favorite);
    renderInfo(it, d);
  }, () => {});
}

function renderInfo(it, d) {
  const isVid = it.kind === "video";
  const m = d || it;
  const rows = [
    ["时间", fmtTime(m.taken_at)], ["尺寸", `${m.width}×${m.height}`],
    ["大小", fmtSize(m.size)], ["格式", (m.ext || "").replace(".", "").toUpperCase()],
  ];
  // 视频没有光圈快门那套 EXIF，换成时长/帧率/编码
  if (isVid) {
    rows.push(["时长", m.duration ? fmtDur(m.duration) : "—"]);
    if (m.fps) rows.push(["帧率", m.fps + " fps"]);
    if (m.vcodec) rows.push(["编码", m.vcodec]);
  } else {
    rows.push(
      ["相机", [m.camera_make, m.camera_model].filter(Boolean).join(" ") || "—"],
      ["镜头", m.lens || "—"],
      ["参数", [m.aperture && "f/" + m.aperture, m.shutter && m.shutter + "s",
        m.iso && "ISO " + m.iso, m.focal && m.focal + "mm"].filter(Boolean).join("  ") || "—"],
      ["画质评分", m.quality ? Math.round(m.quality) : "—"]);
  }
  const groups = (d && d.people_groups) || it.people_groups || [];
  const people = groups.map(p =>
    `<span class="chip2 b" data-pid="${p.id}" title="点击移出">${esc(p.name)} <i class="x">×</i></span>`
  ).join("");
  const tags = (m.tags || []).map(t =>
    `<span class="chip2">${esc(typeof t === "string" ? t : t.tag)}</span>`).join("");
  $("#v-info-body").innerHTML = `
    <h4>基本信息</h4><div class="rows-wrap">
      ${rows.map(r => `<div class="rows"><span class="k">${r[0]}</span><span class="v">${esc(r[1])}</span></div>`).join("")}
    </div>
    <h4>人物</h4><div class="chiprow">${people || `<span class="muted">未识别</span>`}
      <button class="chip2" id="v-p-add">归到…</button></div>
    ${it.place ? `<h4>地点</h4><div class="rows"><span class="k">位置</span>
      <span class="v">${esc(it.place)}</span></div>
      ${m.gps_lat ? `<div class="v-map"><a class="v-link" target="_blank"
        href="https://uri.amap.com/marker?position=${m.gps_lon},${m.gps_lat}">在地图中打开</a></div>` : ""}` : ""}
    ${tags ? `<h4>事物</h4><div class="chiprow">${tags}</div>` : ""}
    <h4>色彩直方图</h4><canvas id="v-hist" width="286" height="64" class="v-hist"></canvas>
    <h4>文件</h4><div class="rows"><span class="k">路径</span><span class="v">${esc(m.path)}</span></div>`;
  // 人物纠错：点已归属的名字移出；「归到…」把这张手动放进某个人物组
  $$("#v-info-body .chip2[data-pid]").forEach(el => el.onclick = async () => {
    await post(`/api/people/${el.dataset.pid}/detach`, { photo_id: m.id, person_id: 0 });
    toast("已从该人物移出");
    renderInfo(it, await api("/api/photo/" + m.id));   // 重新拉一份，避免残影
    route();
  });
  const addBtn = $("#v-p-add");
  if (addBtn) addBtn.onclick = async () => {
    const all = (await api("/api/people")).filter(p => p.kind !== "group");
    if (!all.length) return toast("还没有人物分组");
    const top = all.slice(0, 20);
    const list = top.map((p, i) => `${i + 1}. ${p.name}（${p.photo_count} 张）`).join("\n");
    const pick = prompt(`归到哪个人物？\n${list}\n输入序号：`);
    const t = top[Number(pick) - 1];
    if (!t) return;
    await post("/api/people/assign", { photo_id: m.id, person_id: t.id });
    toast(`已归到「${esc(t.name)}」`);
    route();
  };
  drawHist(d && d.histogram);
}

function drawHist(h) {
  const cv = $("#v-hist");
  if (!cv) return;
  const c = cv.getContext("2d"), w = cv.width, hh = cv.height;
  c.clearRect(0, 0, w, hh);        // 换图先清空，绝不把上一张的直方图留着
  if (!h) return;
  [["r", "#ff5a5a"], ["g", "#5ad35a"], ["b", "#5a9bff"]].forEach(([k, col]) => {
    const arr = h[k], max = Math.max(...arr, 1), bw = w / arr.length;
    c.fillStyle = col + "99";
    arr.forEach((v, i) => c.fillRect(i * bw, hh - (v / max) * hh, bw - 1, (v / max) * hh));
  });
}

/* ---------------- 编辑（另存副本） ---------------- */
/* 编辑只做「不改原图」的事：所有操作先在 1600px 预览图上实时合成，
   保存时把同一串操作在原分辨率上重放一遍，再上传给后端另存 + 入库。 */
const ED = {
  on: false, it: null, img: null, src: null, ops: [], seq: 0,
  b: 100, c: 100, s: 100,
  cropOn: false, drag: null, pending: null, busy: false, dw: 0, dh: 0,
};
const PREVIEW_MAX = 1600;
const edCv = $("#v-edit-cv"), edMask = $("#v-edit-mask"), edSel = $("#v-edit-sel");

function edCanvas(w, h) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}
/* 调色交给 filter，与导出时 ctx.filter 用同一组百分比，预览=成片 */
function edFilter() {
  const p = [];
  if (ED.b !== 100) p.push(`brightness(${ED.b}%)`);
  if (ED.c !== 100) p.push(`contrast(${ED.c}%)`);
  if (ED.s !== 100) p.push(`saturate(${ED.s}%)`);
  return p.join(" ") || "none";
}
function edStyle() { edCv.style.filter = edFilter(); }

/* 操作序列：rot / flip / crop（裁剪用 0~1 归一化坐标，换分辨率重放也一致） */
function edApply(src, ops) {
  let cur = src;
  for (const op of ops) {
    const w = cur.width, h = cur.height;
    let c, g;
    if (op.t === "rot") {
      c = edCanvas(h, w); g = c.getContext("2d");
      g.translate(c.width / 2, c.height / 2);
      g.rotate(op.v * Math.PI / 2);
      g.drawImage(cur, -w / 2, -h / 2);
    } else if (op.t === "flip") {
      c = edCanvas(w, h); g = c.getContext("2d");
      g.translate(w / 2, h / 2);
      g.scale(op.v === "h" ? -1 : 1, op.v === "v" ? -1 : 1);
      g.drawImage(cur, -w / 2, -h / 2);
    } else if (op.t === "crop") {
      c = edCanvas(op.r.w * w, op.r.h * h); g = c.getContext("2d");
      g.drawImage(cur, -Math.round(op.r.x * w), -Math.round(op.r.y * h));
    } else continue;
    cur = c;
  }
  return cur;
}
function edOutSize() {
  let w = ED.dw, h = ED.dh;
  for (const op of ED.ops) {
    if (op.t === "rot") { const t = w; w = h; h = t; }
    else if (op.t === "crop") { w = Math.round(op.r.w * w); h = Math.round(op.r.h * h); }
  }
  return [Math.max(1, w), Math.max(1, h)];
}
function edBuild() {
  if (!ED.src) return;
  const out = edApply(ED.src, ED.ops);
  edCv.width = out.width; edCv.height = out.height;
  edCv.getContext("2d").drawImage(out, 0, 0);
  edStyle();
  const [w, h] = edOutSize();
  $("#ve-size").textContent = `${w} × ${h}`;
}
function edSliders(b = 100, c = 100, s = 100) {
  ED.b = b; ED.c = c; ED.s = s;
  $("#ve-b").value = b; $("#ve-b-v").textContent = b;
  $("#ve-c").value = c; $("#ve-c-v").textContent = c;
  $("#ve-s").value = s; $("#ve-s-v").textContent = s;
  edStyle();
}
function edImg(src) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => rej(new Error("图片解码失败"));
    im.src = src;
  });
}
async function edLoad(id) {
  try { return await edImg("/api/image/" + id); }
  catch (_) { return await edImg("/api/edit-source/" + id); }   // HEIC/TIFF 交给后端转码
}

async function edOpen() {
  const it = V.list[V.i];
  if (!it || it.kind === "video" || ED.busy) return;
  setInfo(false);
  stopPlay();
  ED.it = it; ED.on = true; ED.ops = []; ED.dw = it.width || 0; ED.dh = it.height || 0;
  const seq = ++ED.seq;
  edSliders();
  $("#viewer").classList.add("edit-on");
  $("#v-edit").classList.add("on");
  busy(true);
  try {
    const im = await edLoad(it.id);
    if (!ED.on || seq !== ED.seq) return;   // 加载期间已经退出/换了照片，别把旧图塞回来
    ED.img = im;
    ED.dw = im.naturalWidth; ED.dh = im.naturalHeight;
    const k = Math.min(1, PREVIEW_MAX / Math.max(ED.dw, ED.dh));
    const sc = edCanvas(ED.dw * k, ED.dh * k);
    sc.getContext("2d").drawImage(im, 0, 0, sc.width, sc.height);
    ED.src = sc;
    edBuild();
  } catch (e) {
    edExit();
    toast("这张图打不开，无法编辑：" + esc(e.message || e), 4000);
  } finally { busy(false); }
}
function edExit() {
  if (!ED.on) return;
  ED.on = false; ED.it = null; ED.img = null; ED.src = null; ED.ops = [];
  ED.seq++;
  ED.dw = ED.dh = 0;
  edEndCrop();
  $("#viewer").classList.remove("edit-on");
  $("#v-edit").classList.remove("on");
  edCv.width = edCv.height = 0;
  edCv.style.filter = "none";
}

/* 裁剪：在画面上拖出矩形，归一化存下来后再压进操作序列 */
function edStartCrop() {
  if (!ED.on) return;
  ED.cropOn = true; ED.pending = null;
  edMask.hidden = false;
  edSel.style.display = "none";
  $("#ve-crop").hidden = false;
  $("#ve-crop-ok").disabled = true;
}
function edEndCrop() {
  ED.cropOn = false; ED.drag = null; ED.pending = null;
  edMask.hidden = true;
  edSel.style.display = "none";
  $("#ve-crop").hidden = true;
  $("#ve-crop-ok").disabled = true;
}
edMask.addEventListener("pointerdown", e => {
  if (!ED.cropOn) return;
  const r = edCv.getBoundingClientRect();
  if (!r.width || !r.height) return;
  const x = e.clientX - r.left, y = e.clientY - r.top;
  if (x < -4 || y < -4 || x > r.width + 4 || y > r.height + 4) return;   // 画面外不开始
  e.preventDefault();
  try { edMask.setPointerCapture(e.pointerId); } catch (_) {}
  ED.drag = { x0: Math.min(r.width, Math.max(0, x)), y0: Math.min(r.height, Math.max(0, y)), r };
  ED.pending = null;
  edSel.style.display = "none";
  $("#ve-crop-ok").disabled = true;
});
edMask.addEventListener("pointermove", e => {
  if (!ED.drag) return;
  const r = ED.drag.r;
  const x = Math.min(r.width, Math.max(0, e.clientX - r.left));
  const y = Math.min(r.height, Math.max(0, e.clientY - r.top));
  const x0 = Math.min(ED.drag.x0, x), y0 = Math.min(ED.drag.y0, y);
  const w = Math.abs(x - ED.drag.x0), h = Math.abs(y - ED.drag.y0);
  edSel.style.left = (r.left + x0) + "px";
  edSel.style.top = (r.top + y0) + "px";
  edSel.style.width = w + "px";
  edSel.style.height = h + "px";
  edSel.style.display = "block";
  ED.pending = { x: x0 / r.width, y: y0 / r.height, w: w / r.width, h: h / r.height };
});
function edCropEnd() {
  if (!ED.drag) return;
  ED.drag = null;
  const p = ED.pending;
  if (!p || p.w < 0.02 || p.h < 0.02) {       // 手滑点一下不算裁剪
    ED.pending = null;
    edSel.style.display = "none";
    $("#ve-crop-ok").disabled = true;
    return;
  }
  $("#ve-crop-ok").disabled = false;
}
edMask.addEventListener("pointerup", edCropEnd);
edMask.addEventListener("pointercancel", edCropEnd);
$("#ve-crop").onclick = edStartCrop;
$("#ve-crop-cancel").onclick = edEndCrop;
$("#ve-crop-ok").onclick = () => {
  if (!ED.pending) return;
  ED.ops.push({ t: "crop", r: ED.pending });
  edEndCrop();
  edBuild();
};

function edPush(op) {
  if (!ED.on || ED.cropOn) return;
  ED.ops.push(op);
  edBuild();
}
$("#ve-rot-l").onclick = () => edPush({ t: "rot", v: -1 });
$("#ve-rot-r").onclick = () => edPush({ t: "rot", v: 1 });
$("#ve-flip-h").onclick = () => edPush({ t: "flip", v: "h" });
$("#ve-flip-v").onclick = () => edPush({ t: "flip", v: "v" });
$("#ve-reset").onclick = () => {
  if (ED.cropOn) edEndCrop();
  ED.ops = [];
  edSliders();
  edBuild();
};
$("#ve-cancel").onclick = edExit;
$("#v-edit").onclick = () => { ED.on ? edExit() : edOpen(); };
async function vRotate(delta) {
  const it = V.list[V.i];
  if (!it || it.kind !== "video") return;
  try {
    const r = await post(`/api/photo/${it.id}/rotate?angle=${delta}`, {});
    it.rotate = r.rotate;
    ROT[it.id] = r.rotate;
    vVid.style.transform = r.rotate ? `rotate(${r.rotate}deg)` : "";
    vVid.classList.toggle("rot90", r.rotate === 90 || r.rotate === 270);
    vVid.poster = thumb(it.id, "m");
    toast(`已旋转到 ${r.rotate}°（只改显示，原视频未改动）`);
  } catch (e) { toast("旋转失败：" + esc(e)); }
}
$("#v-rotl").onclick = () => vRotate(-90);
$("#v-rotr").onclick = () => vRotate(90);

/* 实况照片：在同一舞台上播放配对的短视频，看完退回静态图 */
$("#v-live").onclick = () => {
  const it = V.list[V.i];
  if (!it || !it.is_live) return;
  vStage.classList.add("video-on");
  vVid.classList.remove("rot90");
  vVid.style.transform = "";
  vVid.dataset.id = "live-" + it.id;
  vVid.poster = thumb(it.id, "m");
  vVid.src = "/api/live/" + it.id;
  vVid.play().catch(() => {});
  toast("正在播放实况（原照片未改动）");
};

/* 隐藏 / 取消隐藏当前照片：只改显示标记，文件还在原位置 */
$("#v-hide").onclick = async () => {
  const it = V.list[V.i];
  if (!it) return;
  const hide = !it.hidden;
  try {
    await post("/api/photos/batch/hide", { ids: [it.id], value: hide });
    it.hidden = hide ? 1 : 0;
    closeViewer();
    toastUndo(hide ? "已隐藏，可在「隐藏」页找回" : "已取消隐藏");
    route(); renderSide();
  } catch (e) { toast("操作失败：" + esc(e)); }
};
$("#ve-b").oninput = e => { ED.b = +e.target.value; $("#ve-b-v").textContent = ED.b; edStyle(); };
$("#ve-c").oninput = e => { ED.c = +e.target.value; $("#ve-c-v").textContent = ED.c; edStyle(); };
$("#ve-s").oninput = e => { ED.s = +e.target.value; $("#ve-s-v").textContent = ED.s; edStyle(); };

async function edSave() {
  if (!ED.on || ED.busy || ED.cropOn) return;
  const it = ED.it;
  ED.busy = true;
  $("#ve-save").disabled = true;
  busy(true);
  try {
    // 原分辨率重放同一串操作，再套调色
    const full = edCanvas(ED.dw, ED.dh);
    full.getContext("2d").drawImage(ED.img, 0, 0, ED.dw, ED.dh);
    const out = edApply(full, ED.ops);
    const dst = edCanvas(out.width, out.height);
    const g = dst.getContext("2d");
    g.filter = edFilter();
    g.drawImage(out, 0, 0);
    const blob = await new Promise((res, rej) =>
      dst.toBlob(b => b ? res(b) : rej(new Error("生成图片失败")), "image/jpeg", 0.92));
    const res = await fetch(`/api/photo/${it.id}/edit-copy`, {
      method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob,
    }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e.detail || r.statusText)))
      .catch(e => Promise.reject(typeof e === "string" ? e : (e.detail || e.message)));
    // 大图几个 canvas 叠着很吃内存，存完立刻缩到 0
    for (const c of new Set([full, out, dst])) { c.width = c.height = 0; }
    toast(`已保存副本「${esc(res.name)}」`, 3200);
    edExit();
    closeViewer();
    renderSide();
    await route();
    const d = await api("/api/photo/" + res.id);
    openViewer([d], 0);
  } catch (e) {
    toast("保存失败：" + esc(e && e.message ? e.message : e), 4200);
  } finally {
    ED.busy = false;
    $("#ve-save").disabled = false;
    busy(false);
  }
}
$("#ve-save").onclick = edSave;

/* ---------------- 缩放 / 平移 ---------------- */
const vStage = $(".v-stage");
const Z_MAX = 8, Z_DBL = 2.5, Z_STEP = 1.25;
/* transform 是 translate(x,y) scale(z)，原点取图片左上角（transform-origin:0 0）。
   图片用绝对定位 + margin:auto 居中，所以未缩放时它的左上角在舞台坐标里就是 (x0, y0)。 */
const VZ = { z: 1, tx: 0, ty: 0, w0: 0, h0: 0, x0: 0, y0: 0, moved: false };

function vBox() {
  VZ.w0 = vFront.offsetWidth; VZ.h0 = vFront.offsetHeight;  // layout 尺寸，不受 transform 影响
  VZ.x0 = (vStage.clientWidth - VZ.w0) / 2;
  VZ.y0 = (vStage.clientHeight - VZ.h0) / 2;
}
function vApply() {
  const t = (VZ.z === 1 && !VZ.tx && !VZ.ty) ? ""
    : `translate(${VZ.tx}px, ${VZ.ty}px) scale(${VZ.z})`;
  vImgA.style.transform = t;      // 两张都同步，切到另一张时不会跳位
  vImgB.style.transform = t;
  vStage.classList.toggle("zoomed", VZ.z > 1.01);
}
/* 夹紧位移：放大到超出舞台时不许拖出黑边，缩回后自动回居中 */
function vClamp() {
  const sw = vStage.clientWidth, sh = vStage.clientHeight;
  const w = VZ.z * VZ.w0, h = VZ.z * VZ.h0;
  VZ.tx = w >= sw ? Math.min(-VZ.x0, Math.max(sw - w - VZ.x0, VZ.tx)) : (sw - w) / 2 - VZ.x0;
  VZ.ty = h >= sh ? Math.min(-VZ.y0, Math.max(sh - h - VZ.y0, VZ.ty)) : (sh - h) / 2 - VZ.y0;
}
function vReset() {
  VZ.z = 1; VZ.tx = 0; VZ.ty = 0; VZ.moved = false;
  vImgA.style.transform = "";         // 去掉 inline transform，位置交回 margin:auto 居中
  vImgB.style.transform = "";
  vStage.classList.remove("zoomed", "dragging");
}
/* 以舞台内坐标 (cx,cy) 为锚点缩放到 z2：锚点下的那个像素保持不动 */
function vZoomAt(z2, cx, cy) {
  vBox();
  z2 = Math.min(Z_MAX, Math.max(1, z2));
  if (Math.abs(z2 - VZ.z) < 1e-4) return;
  const u = (cx - VZ.x0 - VZ.tx) / VZ.z;
  const v = (cy - VZ.y0 - VZ.ty) / VZ.z;
  VZ.z = z2;
  VZ.tx = cx - VZ.x0 - z2 * u;
  VZ.ty = cy - VZ.y0 - z2 * v;
  vClamp(); vApply();
}
function vZoomCenter(k) {
  vZoomAt(VZ.z * k, vStage.clientWidth / 2, vStage.clientHeight / 2);
}
function vPan(dx, dy) {
  if (VZ.z <= 1.01) return;
  vBox();
  VZ.tx += dx; VZ.ty += dy;
  vClamp(); vApply();
}

/* 滚轮缩放。必须 passive:false，否则 preventDefault 不生效、页面会跟着滚 */
vStage.addEventListener("wheel", e => {
  e.preventDefault();
  if (ED.on) return;               // 编辑态不让滚轮把预览图也缩走
  const r = vStage.getBoundingClientRect();
  vZoomAt(VZ.z * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
}, { passive: false });

vStage.addEventListener("dblclick", e => {
  if (ED.on) return;
  const r = vStage.getBoundingClientRect();
  if (VZ.z > 1.01) vReset();
  else vZoomAt(Z_DBL, e.clientX - r.left, e.clientY - r.top);
});

/* 拖动平移 + 双指捏合。指针集合也用来判断「这次到底拖没拖过」——
   拖完浏览器仍会补一发 click，得靠 VZ.moved 把它和「点按切换工具栏」区分开。 */
const vPts = new Map();
let vDrag = null, vPinch = null;
const vDist = () => { const [a, b] = [...vPts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
const vMid = () => { const [a, b] = [...vPts.values()]; return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };

vStage.addEventListener("pointerdown", e => {
  if (ED.on) return;               // 编辑/裁剪的指针操作交给编辑层自己处理
  if (e.pointerType === "mouse" && e.button !== 0) return;
  vPts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  try { vStage.setPointerCapture(e.pointerId); } catch (_) {}
  if (vPts.size === 2) {                      // 第二指落下 → 转捏合
    vBox();
    vPinch = { d0: Math.max(1, vDist()), z0: VZ.z };
    vDrag = null;
    return;
  }
  if (VZ.z <= 1.01) return;                   // 没放大就不接管，让点按和翻页照常
  vDrag = { id: e.pointerId, x: e.clientX, y: e.clientY, tx: VZ.tx, ty: VZ.ty, moved: false };
});
vStage.addEventListener("pointermove", e => {
  if (!vPts.has(e.pointerId)) return;
  vPts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (vPinch && vPts.size === 2) {
    const r = vStage.getBoundingClientRect(), m = vMid();
    vZoomAt(vPinch.z0 * vDist() / vPinch.d0, m.x - r.left, m.y - r.top);
    return;
  }
  if (!vDrag || e.pointerId !== vDrag.id) return;
  const dx = e.clientX - vDrag.x, dy = e.clientY - vDrag.y;
  if (!vDrag.moved && Math.hypot(dx, dy) > 4) {   // 超过 4px 才算拖动，免得点按被判成拖
    vDrag.moved = true;
    VZ.moved = true;
    vStage.classList.add("dragging");
  }
  if (!vDrag.moved) return;
  VZ.tx = vDrag.tx + dx; VZ.ty = vDrag.ty + dy;
  vClamp(); vApply();
});
function vEndPointer(e) {
  if (!vPts.has(e.pointerId)) return;
  vPts.delete(e.pointerId);
  if (vPts.size < 2) vPinch = null;
  vStage.classList.remove("dragging");
  try { vStage.releasePointerCapture(e.pointerId); } catch (_) {}
  if (vDrag && e.pointerId === vDrag.id) {
    // click 紧跟在 pointerup 后面，延后一拍再清标记
    if (vDrag.moved) setTimeout(() => { VZ.moved = false; }, 0);
    vDrag = null;
  }
}
vStage.addEventListener("pointerup", vEndPointer);
vStage.addEventListener("pointercancel", vEndPointer);

window.addEventListener("resize", () => {
  if (!$("#viewer").classList.contains("open")) return;
  vBox(); vClamp(); vApply();
});

/* ---------------- 交互 ---------------- */
$("#v-close").onclick = closeViewer;
$("#v-prev").onclick = e => { e.stopPropagation(); step(-1); };
$("#v-next").onclick = e => { e.stopPropagation(); step(1); };

/* 信息面板开关。关掉后舞台重新变宽，要等过渡结束再夹紧一次，图片才会重新居中 */
function infoOpen() { return $("#viewer").classList.contains("info-on"); }
function setInfo(on) {
  $("#viewer").classList.toggle("info-on", on);
  $("#v-info-btn").classList.toggle("on", on);
  if (on) $("#v-info").scrollTop = 0;
  setTimeout(() => { vBox(); vClamp(); vApply(); }, 340);
}

// 拖过就别再切工具栏了：拖动结束时浏览器还会补一发 click。
// 点在视频上是在操作播放器（播放/静音/拖进度），顺手把工具栏藏了会很烦。
// 信息面板开着时，点画面任意位置 = 关掉面板（不要顺带把顶栏也藏了）。
$(".v-stage").onclick = e => {
  if (ED.on) return;               // 编辑态不藏工具栏，也别点一下就退出去
  if (e.target.closest("video")) return;
  if (VZ.moved) return;
  if (infoOpen()) setInfo(false);
  else $("#viewer").classList.toggle("chrome-off");
};
$("#v-info-btn").onclick = () => setInfo(!infoOpen());
$("#v-info-close").onclick = e => { e.stopPropagation(); setInfo(false); };
$("#v-fav").onclick = async () => {
  const it = V.list[V.i];
  const r = await post(`/api/photo/${it.id}/favorite`);
  it.is_favorite = r.favorite;
  $("#v-fav").classList.toggle("on", !!r.favorite);
  toast(r.favorite ? "已加入收藏" : "已取消收藏", 1600);
};
// AVI 这类容器 Chromium 解不了，只能交给系统播放器 —— 顺带还有声音
$("#v-ext").onclick = async () => {
  const it = V.list[V.i];
  if (!it) return;
  try {
    await post(`/api/video/${it.id}/open-ext`);
    toast("已交给系统播放器打开", 2000);
  } catch (e) { toast("打不开：" + esc(e)); }
};

/* 删除单张：三种语义分开——移出索引 / 进最近删除 / 彻底删除 */
let delPending = null;
function askDelete(forceMode) {
  const it = V.list[V.i];
  if (!it) return;
  delPending = it;
  $("#dlg-del-sub").textContent = `${it.name || "这张照片"}`;
  if (forceMode) {
    const r = document.querySelector('#dlg-del input[name="delmode"][value="' + forceMode + '"]');
    if (r) r.checked = true;
    $$("#dlg-del .del-mode").forEach(l =>
      l.classList.toggle("on", l.querySelector("input").checked));
  }
  $("#dlg-del").classList.add("open");
}
$("#v-del").onclick = () => askDelete();
$("#dlg-del-cancel").onclick = () => { $("#dlg-del").classList.remove("open"); delPending = null; };
$("#dlg-del-ok").onclick = async () => {
  const it = delPending;
  const mode = (document.querySelector('#dlg-del input[name="delmode"]:checked') || {}).value || "trash";
  $("#dlg-del").classList.remove("open");
  delPending = null;
  if (!it) return;
  try {
    await post(`/api/photo/${it.id}/delete`, { mode });
  } catch (e) { return toast("删除失败：" + esc(e)); }
  // V.list 就是 S.viewItems，两边都摘一次（同一个数组时第二次自然落空）
  for (const arr of [V.list, S.viewItems]) {
    const k = arr ? arr.indexOf(it) : -1;
    if (k >= 0) arr.splice(k, 1);
  }
  const msg = mode === "purge" ? "已彻底删除原文件"
    : mode === "trash" ? "已移入最近删除，30 天内可恢复"
    : "已从相册移除，原图仍在硬盘上";
  toastUndo(msg);
  if (!V.list.length) closeViewer();
  else { V.i = Math.min(V.i, V.list.length - 1); showPhoto(V.i); }
  renderSide(); route();
};

document.addEventListener("keydown", e => {
  if (!$("#viewer").classList.contains("open")) {
    const typing = /^(input|textarea|select)$/i.test((document.activeElement || {}).tagName || "");
    if (e.key === "Escape") {
      const m = $(".dlg-mask.open");
      if (m) {
        m.classList.remove("open");
        if (m.id === "dlg") S.extractIds = null;
        return;
      }
      if (S.selMode) { e.preventDefault(); selectMode(false); return; }
      $$(".dlg-mask").forEach(x => x.classList.remove("open"));
    } else if (!typing && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
      // Ctrl+A = 全选当前视图，顺带自动进入选择态
      e.preventDefault();
      if (!S.selMode) selectMode(true);
      selectAll();
    } else if (!typing && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      // Ctrl+Z = 撤销上一步（移动 / 最近删除 / 收藏 / 相册 / 改名 / 标签）
      e.preventDefault(); undoLast();
    } else if (!typing && e.key === "Delete" && S.selMode) {
      e.preventDefault();
      if (e.shiftKey) {
        document.querySelector('#dlg-bdel input[name="bdelmode"][value="purge"]').checked = true;
        $$("#dlg-bdel .del-mode").forEach(l =>
          l.classList.toggle("on", l.querySelector("input").checked));
      }
      askBatchDelete();
    } else if (e.key === "/" && document.activeElement !== $("#search")) {
      e.preventDefault(); $("#search").focus();
    }
    return;
  }
  // 编辑态：Esc 先退出编辑，其它快捷键一律不接管（免得方向键把正在编辑的照片翻走）
  if (ED.on) {
    if (e.key === "Escape") { e.preventDefault(); edExit(); }
    return;
  }
  // Esc 的优先级：确认框 → 信息面板 → 整个查看器
  if (e.key === "Escape") {
    const m = $(".dlg-mask.open");
    if (m) m.classList.remove("open");
    else if (infoOpen()) setInfo(false);
    else closeViewer();
  }
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
    e.preventDefault(); undoLast();
  }
  else if (e.key === "Delete") {
    // Shift+Delete = 彻底删除（仍然要过确认框），单按 Delete = 默认最近删除
    askDelete(e.shiftKey ? "purge" : undefined);
  }
  // 放大之后方向键用来平移（翻页交给左右两个圆钮），没放大就是普通翻页
  else if (e.key === "ArrowLeft") { if (VZ.z > 1.01) vPan(-60, 0); else step(-1); }
  else if (e.key === "ArrowRight") { if (VZ.z > 1.01) vPan(60, 0); else step(1); }
  else if (e.key === "ArrowUp" && VZ.z > 1.01) { e.preventDefault(); vPan(0, -60); }
  else if (e.key === "ArrowDown" && VZ.z > 1.01) { e.preventDefault(); vPan(0, 60); }
  else if (e.key === "0") vReset();
  else if (e.key === " " || e.key === "Spacebar") {
    e.preventDefault();
    // 视频时空格 = 播放/暂停这一段片子；照片时才是起停幻灯片
    if (vStage.classList.contains("video-on")) { vVid.paused ? vVid.play() : vVid.pause(); }
    else togglePlay();
  }
  else if (e.key === "+" || e.key === "=") vZoomCenter(Z_STEP);
  else if (e.key === "-" || e.key === "_") vZoomCenter(1 / Z_STEP);
  else if (e.key.toLowerCase() === "f") $("#v-fav").click();
  else if (e.key.toLowerCase() === "i") $("#v-info-btn").click();
  else if (e.key.toLowerCase() === "e") $("#v-edit").click();
  else if (e.key.toLowerCase() === "h") $("#v-hide").click();
});

$("#search").addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  const q = e.target.value.trim();
  if (q) location.hash = "#/search/" + encodeURIComponent(q);
});
$("#zoom").onclick = e => {
  const b = e.target.closest("button"); if (!b) return;
  $$("#zoom button").forEach(x => x.classList.remove("on"));
  b.classList.add("on");
  S.zoom = +b.dataset.z;
  document.documentElement.style.setProperty("--tile", S.zoom + "px");
};
/* 布局切换：网格 / 圆形（精选在中心），本地记住 */
$$("#layout button").forEach(b => b.classList.toggle("on", b.dataset.l === S.layout));
$("#layout").onclick = e => {
  const b = e.target.closest("button"); if (!b) return;
  $$("#layout button").forEach(x => x.classList.remove("on"));
  b.classList.add("on");
  S.layout = b.dataset.l;
  localStorage.setItem("pa.layout", S.layout);
  // 概览/相册列表/最近删除这类页面没有照片网格，直接切过去会「看起来没反应」；
  // 环形模式在它们上面没有意义，统一送到图库
  const noGrid = ["overview", "people", "places", "memories", "things", "albums",
    "folders", "duplicates", "trash", "events", "trips"].includes(S.route.view);
  if (noGrid && S.layout === "round") { location.hash = "#/library"; return; }
  route();
};

/* 顶部后台任务进度条：pct 0~100，text 显示在顶部胶囊里 */
function jobbar(on, pct = 0, text = "") {
  const bar = $("#jobbar");
  if (!on) return bar.classList.remove("on");
  $("#jb-fill").style.width = Math.max(0, Math.min(100, pct)) + "%";
  $("#jb-text").textContent = text;
  bar.classList.add("on");
}

$("#btn-analyze").onclick = async () => {
  try { await post("/api/analyze"); }
  catch (e) { return toast("分析失败：" + esc(e)); }
  toast("AI 分析已开始，可以继续浏览照片，进度看顶部", 5000);
  const timer = setInterval(async () => {
    let s;
    try { s = await api("/api/analyze/status"); }
    catch (_) { return; }
    const total = s.steps || 6, step = s.step_index || 0;
    // 各步平均分摊进度条：已完成整步 + 当前步内比例
    const frac = s.total ? Math.min(1, (s.done || 0) / s.total) : 0;
    const pct = ((step - 1 + (s.status === "running" ? frac : 0)) / total) * 100;
    const speed = s.rate ? ` · ${s.rate} 张/秒` : "";
    jobbar(true, s.status === "running" ? pct : 100,
      `${step}/${total} ${s.step || ""}${s.total ? ` · ${s.done}/${s.total}${speed}` : ""}`);
    if (s.status === "running") return;
    clearInterval(timer);
    setTimeout(() => jobbar(false), 800);
    const r = s.result || {};
    if (s.status === "done") {
      toast(`分析完成：标签 ${r.tagged ?? 0} 条 · 评分 ${r.scored ?? 0} 张 · `
        + `精选 ${r.bursts ?? 0} 组 · 人物 ${r.people ?? 0} 组 · 地点 ${r.places ?? 0} 处`, 9000);
      renderSide(); route();
    } else if (s.status === "cancelled") {
      toast("分析已取消");
    } else {
      toast("分析失败：" + esc(s.error || "未知错误"));
    }
  }, 1000);
};

$("#btn-export").onclick = async () => {
  const name = prompt("相册包名称（留空自动命名）：") || undefined;
  toast("正在导出，请稍候…", 6000);
  try {
    const r = await post("/api/export", { ids: [], name });
    toast(`已导出 ${r.count} 张 → ${esc(r.zip)}（zip 可直接发送）`, 8000);
  } catch (e) { toast("导出失败：" + esc(e)); }
};

/* ---------------- 整理到文件夹 ---------------- */
$$(".dlg-mask").forEach(m => m.onclick = e => {
  if (e.target !== m) return;
  m.classList.remove("open");
  if (m.id === "dlg") S.extractIds = null;
});
$("#btn-extract").onclick = () => {
  S.extractIds = null;
  const { label, f } = currentFilter();
  const n = f.ids ? f.ids.length : S.total;
  $("#dlg-sub").textContent = `范围：${label} · 共 ${n || 0} 张（可复制出去修图后放回）`;
  $("#dlg-mode").value = "copy";
  $("#dlg").classList.add("open");
  $("#dlg-dir").focus();
};

/* ---------------- 选择态与批量操作 ---------------- */
$("#btn-select").onclick = () => selectMode(!S.selMode);
$("#sb-done").onclick = () => selectMode(false);
$("#sb-all").onclick = selectAll;
$("#sb-fav").onclick = () => batchFav(true);
$("#sb-unfav").onclick = () => batchFav(false);
$("#sb-del").onclick = askBatchDelete;
$("#dlg-bdel-cancel").onclick = () => $("#dlg-bdel").classList.remove("open");
$("#dlg-bdel-ok").onclick = async () => {
  const ids = selIds();
  const mode = (document.querySelector('#dlg-bdel input[name="bdelmode"]:checked') || {}).value || "trash";
  $("#dlg-bdel").classList.remove("open");
  if (!ids.length) return;
  try {
    const r = await post("/api/photos/batch/delete", { ids, mode });
    const msg = mode === "purge" ? `已彻底删除 ${r.count} 张原文件`
      : mode === "trash" ? `已把 ${r.count} 张移入最近删除`
      : `已从相册移除 ${r.count} 张，原图仍在硬盘上`;
    toastUndo(msg + (r.failed && r.failed.length ? `，${r.failed.length} 张失败` : ""));
  } catch (e) { return toast("删除失败：" + esc(e)); }
  selectMode(false);
  renderSide(); route();
};

/* ---------------- 批量加入相册 / 标签 / 重命名 ---------------- */
let albumPickId = null;
async function openAlbumPicker() {
  if (!S.sel.size) return;
  albumPickId = null;
  $("#dlg-album-sub").textContent = `把已选的 ${S.sel.size} 张照片加入相册`;
  $("#dlg-album-name").value = "";
  $("#album-pick").innerHTML = "加载中…";
  $("#dlg-album").classList.add("open");
  try {
    const list = await api("/api/albums");
    $("#album-pick").innerHTML = list.length
      ? list.map(a => `<button class="album-opt" data-aid="${a.id}">
          ${esc(a.name)}<em>${a.c}</em></button>`).join("")
      : `<span class="hint">还没有相册，直接在下面新建一个</span>`;
    $$("#album-pick [data-aid]").forEach(b => b.onclick = () => {
      albumPickId = Number(b.dataset.aid);
      $$("#album-pick .album-opt").forEach(x => x.classList.toggle("on", x === b));
    });
  } catch (e) { $("#album-pick").textContent = "读取相册失败：" + e; }
}
$("#sb-album").onclick = openAlbumPicker;
$("#dlg-album-cancel").onclick = () => $("#dlg-album").classList.remove("open");
$("#dlg-album-ok").onclick = async () => {
  const ids = selIds();
  const name = $("#dlg-album-name").value.trim();
  $("#dlg-album").classList.remove("open");
  if (!ids.length) return;
  try {
    let aid = albumPickId;
    if (name) aid = (await post("/api/albums", { name })).id;
    if (!aid) return toast("请选择或新建一个相册");
    const r = await post(`/api/albums/${aid}/add`, { ids });
    toastUndo(`已把 ${r.count} 张加入相册`);
    renderSide();
  } catch (e) { toast("加入失败：" + esc(e)); }
};

$("#sb-tag").onclick = () => {
  if (!S.sel.size) return;
  $("#dlg-tag-sub").textContent = `给已选的 ${S.sel.size} 张照片批量加/减标签`;
  $("#dlg-tag-name").value = "";
  $("#dlg-tag").classList.add("open");
  $("#dlg-tag-name").focus();
};
$("#dlg-tag-cancel").onclick = () => $("#dlg-tag").classList.remove("open");
function closeTagDlg() { $("#dlg-tag").classList.remove("open"); }
async function doBatchTag(action) {
  const ids = selIds();
  const tag = $("#dlg-tag-name").value.trim();
  if (!tag) return toast("请填写标签");
  closeTagDlg();
  try {
    const r = await post("/api/photos/batch/tag", { ids, tag, action });
    toastUndo(`已${action === "remove" ? "移除" : "添加"}标签「${esc(tag)}」`);
  } catch (e) { toast("操作失败：" + esc(e)); }
}
$("#dlg-tag-ok").onclick = () => doBatchTag("add");
$("#dlg-tag-remove").onclick = () => doBatchTag("remove");

$("#sb-rename").onclick = () => {
  if (!S.sel.size) return;
  $("#dlg-rename-sub").textContent = `将重命名已选的 ${S.sel.size} 张照片（只改文件名，不移动位置）`;
  $("#dlg-rename").classList.add("open");
  $("#dlg-rename-tpl").focus();
};
$("#dlg-rename-cancel").onclick = () => $("#dlg-rename").classList.remove("open");
$("#dlg-rename-ok").onclick = async () => {
  const ids = selIds();
  const template = $("#dlg-rename-tpl").value.trim() || "{date}_{seq}";
  $("#dlg-rename").classList.remove("open");
  try {
    const r = await post("/api/photos/batch/rename", { ids, template });
    toastUndo(`已重命名 ${r.count} 张` +
      (r.failed && r.failed.length ? `，${r.failed.length} 张失败` : ""));
    if (r.failed && r.failed.length) showReport("重命名结果", r.failed.map(f => ({
      name: "照片 #" + f.id, reason: f.msg })));
    selectMode(false);
    route(); renderSide();
  } catch (e) { toast("重命名失败：" + esc(e)); }
};

/* 导入报告 / 失败清单：不弹一串 alert，统一走一个只读面板 */
function showReport(title, rows) {
  $("#report-body").innerHTML = `<p class="dlg-sub">${esc(title)}</p>` +
    (rows.length ? `<div class="report-list">${rows.map(r =>
      `<div class="report-row"><b>${esc(r.name || "")}</b><span>${esc(r.reason || "")}</span></div>`).join("")}</div>`
      : `<p class="hint">没有需要列出的条目</p>`);
  $("#dlg-report").classList.add("open");
}
$("#report-close").onclick = () => $("#dlg-report").classList.remove("open");
/* 分享：优先复制到「分享文件夹」，方便直接拖进微信/邮件；也可以退回打包 ZIP */
$("#sb-share").onclick = async () => {
  const ids = selIds();
  if (!ids.length) return;
  const last = localStorage.getItem("pa.sharedir");
  let dir = null;
  if (last && confirm(`复制到上次的分享文件夹？\n${last}\n\n点「取消」可以另选文件夹或打包 ZIP`)) {
    dir = last;
  } else {
    dir = await pickFolder("选择分享文件夹（照片会复制一份到这里）");
  }
  if (!dir) {
    if (!confirm("没有选择文件夹。改为打包成 ZIP？")) return;
    const name = prompt("相册包名称（留空自动命名）：") || undefined;
    toast("正在导出，请稍候…", 6000);
    try {
      const r = await post("/api/export", { ids, name });
      toast(`已导出 ${r.count} 张 → ${esc(r.zip)}`, 8000);
      selectMode(false);
    } catch (e) { toast("导出失败：" + esc(e)); }
    return;
  }
  localStorage.setItem("pa.sharedir", dir);
  busy(true);
  try {
    const r = await post("/api/share/copy", { ids, dir });
    busy(false);
    toast(`已复制 ${r.count} 张到分享文件夹 → ${esc(r.dir)}`, 9000);
    if (r.skipped && r.skipped.length) {
      showReport(`分享完成：${r.count} 张成功，${r.skipped.length} 张跳过`, r.skipped);
    }
    selectMode(false);
  } catch (e) { busy(false); toast("分享失败：" + esc(e)); }
};

/* 隐藏所选：隐藏页里则是取消隐藏。只改显示标记，原文件与索引都保留 */
$("#sb-hide").onclick = async () => {
  const ids = selIds();
  if (!ids.length) return;
  const hide = S.route.view !== "hidden";
  try {
    const r = await post("/api/photos/batch/hide", { ids, value: hide });
    toast(`${hide ? "已隐藏" : "已取消隐藏"} ${r.count} 张`);
    selectMode(false);
    route(); renderSide();
  } catch (e) { toast("操作失败：" + esc(e)); }
};
$("#sb-move").onclick = () => {
  const ids = selIds();
  if (!ids.length) return;
  S.extractIds = ids;
  $("#dlg-sub").textContent =
    `范围：已选 ${ids.length} 张（「剪切」会把硬盘上的原文件移到目标文件夹）`;
  $("#dlg-mode").value = "move";
  $("#dlg").classList.add("open");
  $("#dlg-dir").focus();
};
$("#content").addEventListener("pointerdown", boxStart);
$("#dlg-cancel").onclick = () => {
  $("#dlg").classList.remove("open");
  S.extractIds = null;
};
$("#dlg-dir").addEventListener("keydown", e => { if (e.key === "Enter") $("#dlg-ok").click(); });
$("#dlg-browse").onclick = async () => {
  const p = await pickFolder("选择整理到的目标文件夹");
  if (p) $("#dlg-dir").value = p;
};

/* 弹系统「选择文件夹」窗口。
   原生窗口里用 pywebview 自己的对话框（window.pywebview.api）；
   浏览器模式拿不到本地路径，只能由本地服务端来弹。 */
async function pickFolder(title) {
  const pv = window.pywebview && window.pywebview.api;
  if (pv && pv.pick_folder) {
    busy(true);
    try {
      const p = await pv.pick_folder(title);
      return p ? String(p) : null;
    } catch (e) { toast("无法打开文件夹选择窗口：" + esc(e)); return null; }
    finally { busy(false); }
  }
  busy(true);
  try {
    const r = await api("/api/pick-folder?title=" + encodeURIComponent(title));
    if (!r.ok) { toast("打不开系统文件夹窗口，可以直接手动粘贴路径", 4200); return null; }
    return r.path;
  } catch (e) { toast("无法打开文件夹选择窗口：" + esc(e)); return null; }
  finally { busy(false); }
}

/* ---------------- 导入（系统文件夹选择器） ---------------- */
let impDirs = [];
function renderImpList() {
  $("#imp-list").innerHTML = impDirs.length
    ? impDirs.map((d, i) => `<div class="pick-item">
        <span class="pi-path">${esc(d)}</span>
        <button class="pi-del" data-i="${i}" title="移除">×</button></div>`).join("")
    : `<div class="pick-empty">还没有添加文件夹</div>`;
  $$("#imp-list .pi-del").forEach(b => b.onclick = () => {
    impDirs.splice(Number(b.dataset.i), 1); renderImpList();
  });
}
$("#btn-scan").onclick = () => {
  impDirs = []; renderImpList();
  $("#dlg-import").classList.add("open");
};
$("#imp-add").onclick = async () => {
  const p = await pickFolder("选择要导入的照片文件夹");
  if (p && !impDirs.includes(p)) { impDirs.push(p); renderImpList(); }
};
$("#imp-cancel").onclick = () => $("#dlg-import").classList.remove("open");
$("#imp-ok").onclick = async () => {
  if (!impDirs.length) return toast("请先添加至少一个文件夹");
  const dirs = impDirs.slice();
  $("#dlg-import").classList.remove("open");
  try {
    await post("/api/scan", { dirs });
    busy(true);
    let tick = 0, lastNew = 0;
    const timer = setInterval(async () => {
      const s = await api("/api/scan/status");
      tick++;
      if (s.status === "running") {
        const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
        toast(`正在导入 ${pct}% · ${s.done}/${s.total} · 已入库 ${s.new}`
          + (s.speed ? ` · ${s.speed} 张/秒` : "")
          + `<button class="toast-act" id="scan-stop">停止</button>`, 2500);
        const b = $("#scan-stop");
        if (b) b.onclick = () => { b.textContent = "正在停止…"; b.disabled = true; post("/api/scan/stop"); };
        // 每 3 秒刷新一次侧栏数字，导入过程中就能看到库在长大
        if (tick % 3 === 0 && s.new !== lastNew) { lastNew = s.new; renderSide().catch(() => {}); }
        return;
      }
      clearInterval(timer); busy(false);
      const stopped = s.status === "cancelled";
      toast(s.message || (stopped ? `已停止导入，已入库的 ${s.new} 张可以直接使用`
        : `扫描完成：新增 ${s.new} 张，重复跳过 ${s.dups} 张`), 8000);
      const rows = [
        ...(s.failed || []),
        ...(s.dup_names || []).map(n => ({ name: n, reason: "内容重复，图库里已有这张" })),
      ];
      if (rows.length) showReport(`导入${stopped ? "已停止" : "完成"}：${s.new} 张已入库，${rows.length} 张未收录（最多显示 60 条）`, rows);
      renderSide(); route();
    }, 900);
  } catch (e) { busy(false); toast("导入失败：" + esc(e)); }
};

$("#dlg-ok").onclick = async () => {
  const dir = $("#dlg-dir").value.trim();
  if (!dir) return toast("请填写目标文件夹");
  const { f } = currentFilter();
  const mode = $("#dlg-mode").value;
  // 从选择态进来时只处理勾中的那几张；否则沿用当前筛选
  const ids = S.extractIds;
  S.extractIds = null;
  const wasSel = !!(ids && ids.length);
  const body = ids && ids.length
    ? { dir, mode, layout: $("#dlg-layout").value,
        prefix: $("#dlg-prefix").value.trim() || null, ids }
    : { dir, mode, layout: $("#dlg-layout").value,
        prefix: $("#dlg-prefix").value.trim() || null, ...f };
  $("#dlg").classList.remove("open");
  busy(true); toast("正在整理，请稍候…", 6000);
  try {
    const r = await post("/api/extract", body);
    if (!r.total) { busy(false); return toast("当前筛选没有匹配到照片"); }
    const timer = setInterval(async () => {
      const s = await api("/api/extract/status");
      if (s.status === "running") return toast(`正在整理 ${s.done}/${s.total}…`, 3000);
      clearInterval(timer); busy(false);
      const verb = s.mode === "move" ? "剪切" : "复制";
      const msg = `已${verb} ${s.count} 张 → ${esc(s.dir)}`
        + (s.skipped ? `（跳过 ${s.skipped} 张）` : "");
      if (s.mode === "move" && s.count) toastUndo(msg); else toast(msg, 9000);
      if (s.skipped_detail && s.skipped_detail.length) {
        showReport(`整理完成：${s.count} 张成功，${s.skipped} 张跳过`, s.skipped_detail);
      }
      if (wasSel) {
        selectMode(false);
        renderSide();
        if (s.mode === "move") route();   // 剪切后索引路径已改，重载当前视图
      }
    }, 700);
  } catch (e) { busy(false); toast("整理失败：" + esc(e)); }
};

/* ---------------- 外观与维护 ---------------- */
function renderThemeDlg() {
  const curStyle = document.documentElement.dataset.style || "glass";
  const curAccent = document.documentElement.dataset.accent || "blue";
  const curMode = window.PATheme.mode();
  $("#style-grid").innerHTML = STYLES.map(([id, name, desc]) =>
    `<button class="style-card${id === curStyle ? " on" : ""}" data-style="${id}">
      <span class="sc-prev" data-s="${id}"></span><b>${name}</b><span>${desc}</span></button>`).join("");
  $("#mode-row").innerHTML = MODES.map(([id, name]) =>
    `<button data-mode="${id}" class="${id === curMode ? "on" : ""}">${name}</button>`).join("");
  $("#accent-row").innerHTML = ACCENTS.map(([id, c]) =>
    `<button class="accent-dot${id === curAccent ? " on" : ""}" data-accent="${id}"
      title="${id}" style="background:${c}"></button>`).join("");
  $$("#style-grid [data-style]").forEach(b => b.onclick = () => {
    applyTheme(b.dataset.style, null);
    $$("#style-grid .style-card").forEach(x => x.classList.toggle("on", x === b));
  });
  $$("#mode-row [data-mode]").forEach(b => b.onclick = () => {
    applyTheme(null, null, b.dataset.mode);
    $$("#mode-row [data-mode]").forEach(x => x.classList.toggle("on", x === b));
  });
  $$("#accent-row [data-accent]").forEach(b => b.onclick = () => {
    applyTheme(null, b.dataset.accent);
    $$("#accent-row .accent-dot").forEach(x => x.classList.toggle("on", x === b));
  });
  loadMaint();
}
async function loadMaint() {
  try {
    const d = await api("/api/maintenance");
    const c = d.check, last = d.backups[0];
    $("#maint-box").innerHTML =
      `照片索引 <b>${c.photos}</b> 条 · 路径失效 <b>${c.missing}</b> · 重复内容 <b>${c.dup_groups}</b> 组<br>` +
      `孤立缩略图 <b>${c.orphan_thumbs}</b> · 最近删除 <b>${c.trash_items}</b> 项（${fmtSize(c.trash_bytes)}）` +
      ` · 索引体积 <b>${fmtSize(c.db_bytes)}</b><br>` +
      `最近备份：${last ? esc(last.name) + "（" + fmtSize(last.size) + "）" : "还没有备份"}`;
  } catch (e) { $("#maint-box").textContent = "读取维护信息失败：" + e; }
}
function openTheme() {
  renderThemeDlg();
  $("#dlg-theme").classList.add("open");
}
$("#btn-theme").onclick = openTheme;
$("#btn-theme2").onclick = openTheme;
$("#theme-close").onclick = () => $("#dlg-theme").classList.remove("open");
$("#maint-refresh").onclick = loadMaint;
$("#maint-backup").onclick = async () => {
  try {
    const r = await post("/api/maintenance/backup");
    toast(`已备份索引（${fmtSize(r.size)}）`, 5000);
    loadMaint();
  } catch (e) { toast("备份失败：" + esc(e)); }
};

/* ---------------- 启动 ---------------- */
renderSide().then(route);
