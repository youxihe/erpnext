// ERPNext POC — 无头浏览器截图工具（容器内运行）
// 用法： SID=<session id> node shot.js "<相对路径>" "<输出文件名>"
// 例：   SID=abc123 node shot.js "/app/desk" poc-01-desk.png
const puppeteer = require("puppeteer-core");

const BASE = "http://localhost:8000";
const OUT_DIR = "/hostshare/screenshots";

(async () => {
  const route = process.argv[2] || "/app/desk";
  const outName = process.argv[3] || "shot.png";
  const sid = process.env.SID;

  if (!sid) {
    console.error("缺少 SID 环境变量");
    process.exit(1);
  }

  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-headless-shell",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 950 });
    await page.setCookie({
      name: "sid",
      value: sid,
      domain: "localhost",
      path: "/",
    });
    await page.goto(BASE + route, {
      waitUntil: "networkidle2",
      timeout: 90000,
    });
    // 等前端 SPA 把界面渲染出来
    await new Promise((r) => setTimeout(r, 6000));
    const title = await page.title();
    await page.screenshot({ path: `${OUT_DIR}/${outName}`, fullPage: false });
    console.log(`OK ${outName} title="${title}" route=${route}`);
  } catch (e) {
    console.error("SHOT_FAILED", e.message);
    process.exit(2);
  } finally {
    await browser.close();
  }
})();
