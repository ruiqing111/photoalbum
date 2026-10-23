/* 主题模块：风格、强调色、明暗模式。只改界面变量，不碰照片与索引。
 *
 * 明暗不再依赖 prefers-color-scheme：由这里解析成 light / dark 写到
 * <html data-theme>，CSS 只认属性。这样用户选「浅色」时不会被系统的
 * 深色模式盖掉；选「跟随系统」时监听系统切换，窗口即时跟着变。
 */
(function () {
  const STYLES = [
    ["glass", "液态玻璃", "半透明 · 多层光晕"],
    ["frost", "朦胧", "强模糊 · 整窗一体"],
    ["minimal", "简洁", "纯色 · 零模糊"],
    ["pixel", "像素", "硬边框 · 点阵"],
    ["comic", "漫画", "粗描边 · 气泡"],
  ];
  const ACCENTS = [
    ["blue", "#007aff"], ["green", "#0f9d58"], ["rose", "#e0367a"],
    ["amber", "#d97706"], ["violet", "#7c3aed"], ["graphite", "#4b5563"],
  ];
  const MODES = [
    ["auto", "跟随系统"], ["light", "浅色"], ["dark", "深色"],
  ];
  const mq = window.matchMedia("(prefers-color-scheme: dark)");

  const mode = () => localStorage.getItem("pa.mode") || "auto";
  const resolve = m => (m === "dark" || (m === "auto" && mq.matches)) ? "dark" : "light";

  function apply(style, accent, m) {
    const root = document.documentElement;
    const s = style || localStorage.getItem("pa.style") || "glass";
    const a = accent || localStorage.getItem("pa.accent") || "blue";
    const md = m || mode();
    root.dataset.style = s;
    root.dataset.accent = a;
    root.dataset.mode = md;
    root.dataset.theme = resolve(md);
    try {
      localStorage.setItem("pa.style", s);
      localStorage.setItem("pa.accent", a);
      localStorage.setItem("pa.mode", md);
    } catch (e) { /* 无痕模式写不了 localStorage，不耽误用 */ }
  }

  // 只在「跟随系统」时响应系统切换；用户手动选过明暗就尊重用户
  mq.addEventListener("change", () => { if (mode() === "auto") apply(null, null, "auto"); });

  apply();
  window.PATheme = { STYLES, ACCENTS, MODES, apply, mode, resolve };
})();
