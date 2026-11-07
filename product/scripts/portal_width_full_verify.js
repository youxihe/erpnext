// /cn_portal 宽度修复完整回归：残留限宽扫描、BOM 标题/评论区、三态、列表页、普通表单、窄视口
const puppeteer = require("puppeteer-core");
const BASE = "http://localhost:8000";
const OUT = "/hostshare/screenshots";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-headless-shell",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const checks = [];
  const check = (name, ok, detail) => checks.push({ name, ok: !!ok, detail });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 950, deviceScaleFactor: 1 });
    await page.setCookie({ name: "sid", value: process.env.SID, domain: "localhost", path: "/" });
    await page.goto(BASE + "/cn_portal", { waitUntil: "networkidle2", timeout: 90000 });
    await page.waitForSelector("#frame");

    const open = async (url) => {
      await page.evaluate((u) => window.openPage(u, "测试"), url);
      await wait(6500);
    };
    const measure = () => page.evaluate(() => {
      const f = document.querySelector("#frame");
      const d = f.contentDocument;
      const shape = (el) => {
        const r = el.getBoundingClientRect(), c = d.defaultView.getComputedStyle(el);
        return { x: Math.round(r.x), w: Math.round(r.width), maxW: c.maxWidth };
      };
      const pick = (sel) => {
        for (const el of d.querySelectorAll(sel)) {
          if (el.getBoundingClientRect().width >= 20) return shape(el);
        }
        return null;
      };
      // 仍有 900px / 700px 原生限宽的可见大块
      const leftovers = [...d.querySelectorAll("*")].filter((el) => {
        const c = d.defaultView.getComputedStyle(el);
        return c.display !== "none" && el.getBoundingClientRect().width >= 250
          && (c.maxWidth === "900px" || c.maxWidth === "700px");
      }).slice(0, 8).map((el) => ({ cls: String(el.className).slice(0, 60), ...shape(el) }));
      // 时间线内容取最宽的一个（第一个可能是操作按钮里的小块）
      let timeline = null;
      for (const el of d.querySelectorAll(".timeline-content")) {
        const s = shape(el);
        if (!timeline || s.w > timeline.w) timeline = s;
      }
      return {
        W: Math.round(f.getBoundingClientRect().width),
        head: pick(".section-head"), grid: pick(".form-grid"), body: pick(".section-body"),
        footer: pick(".form-footer"), comment: pick(".comment-box"),
        afterSave: pick(".after-save"), page: pick(".page-container"),
        timeline, leftovers, contentMax: window.contentMax,
        docW: d.documentElement.scrollWidth, winW: f.contentWindow.innerWidth,
      };
    });

    // ---- 1. BOM 表单（用户反馈页面）
    await open("/desk/bom/BOM-ASSY-X1-001");
    const bom = await measure();
    check("BOM 标题铺满", bom.head && bom.head.w > 1300, bom.head);
    check("BOM 正文铺满", bom.body && bom.body.w > 1300, bom.body);
    check("BOM 页脚(评论/活动)铺满", bom.footer && bom.footer.w > 1300, bom.footer);
    check("BOM 评论框铺满", bom.comment && bom.comment.w > 1300, bom.comment);
    check("BOM 时间线解除 700px", bom.timeline && bom.timeline.maxW === "none" && bom.timeline.w > 1000, bom.timeline);
    check("BOM 无 900/700 限宽残留", bom.leftovers.length === 0, bom.leftovers);
    check("标题与表格左边缘对齐(±20px)", bom.head && bom.grid && Math.abs(bom.head.x - (bom.grid.x - 30)) <= 20, { head: bom.head, grid: bom.grid });
    await page.screenshot({ path: `${OUT}/cn-portal-bom-top-fixed.png` });

    // 滚到评论区（iframe 内是容器滚动，scrollIntoView 最可靠）
    const scrolled = await page.evaluate(() => {
      const d = document.querySelector("#frame").contentDocument;
      const el = d.querySelector(".form-footer");
      if (!el) return "no .form-footer";
      el.scrollIntoView({ block: "end" });
      return "ok";
    });
    await wait(1200);
    check("评论区可滚动到达", scrolled === "ok", scrolled);
    await page.screenshot({ path: `${OUT}/cn-portal-bom-bottom-fixed.png` });

    // ---- 2. 三态切换
    await page.click("#btn-width"); await wait(600);
    const w1200 = await measure();
    check("1200px 模式：标题限宽", w1200.head && w1200.head.w <= 1210 && w1200.head.w >= 1190, w1200.head);
    await page.click("#btn-width"); await wait(600);
    const w900 = await measure();
    check("900px 模式：标题/页脚统一限宽居中",
      w900.head && w900.footer && w900.head.w <= 910 && w900.footer.w <= 910 && w900.head.x > 150,
      { head: w900.head, footer: w900.footer });
    await page.screenshot({ path: `${OUT}/cn-portal-bom-900-fixed.png` });
    await page.click("#btn-width"); await wait(600);
    const wFull = await measure();
    check("切回铺满：页脚恢复", wFull.footer && wFull.footer.w > 1300, wFull.footer);

    // ---- 3. 列表页
    await open("/desk/sales-order");
    const list = await measure();
    check("列表页容器铺满", list.page && list.page.w > 1300, list.page);
    check("列表页无限宽残留", list.leftovers.length === 0, list.leftovers);
    await page.screenshot({ path: `${OUT}/cn-portal-list-fixed.png` });

    // ---- 4. 普通表单（Lead）
    await open("/desk/lead/CRM-LEAD-2026-00003");
    const lead = await measure();
    check("Lead 表单正文铺满", lead.body && lead.body.w > 1300, lead.body);
    check("Lead 表单标题铺满", lead.head && lead.head.w > 1300, lead.head);
    check("Lead 表单无限宽残留", lead.leftovers.length === 0, lead.leftovers);
    await page.screenshot({ path: `${OUT}/cn-portal-lead-fixed.png` });

    // ---- 5. 窄视口自适应
    await page.setViewport({ width: 1100, height: 800 });
    await wait(2000);
    const narrow = await measure();
    check("1100px 视口无横向溢出", narrow.docW <= narrow.winW + 5, { docW: narrow.docW, winW: narrow.winW, W: narrow.W });
    check("1100px 视口标题仍铺满", narrow.head && narrow.head.w > narrow.W - 60, narrow.head);
    await page.screenshot({ path: `${OUT}/cn-portal-narrow-fixed.png` });

    const pass = checks.filter((c) => c.ok).length;
    console.log(JSON.stringify({ pass, total: checks.length, checks }, null, 1));
    console.log(`RESULT ${pass}/${checks.length}`);
    if (pass !== checks.length) process.exitCode = 3;
  } catch (e) {
    console.error("FAILED", e.stack || e.message);
    process.exit(2);
  } finally {
    await browser.close();
  }
})();
