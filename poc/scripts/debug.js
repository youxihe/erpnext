// 诊断 desk 报错：抓取 console / pageerror / 失败请求
const puppeteer = require("puppeteer-core");
const BASE = "http://localhost:8000";

(async () => {
  const route = process.argv[2] || "/app/desk";
  const sid = process.env.SID;
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-headless-shell",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const page = await browser.newPage();
  await page.setCookie({ name: "sid", value: sid, domain: "localhost", path: "/" });

  const logs = [];
  page.on("console", (m) => {
    if (["error", "warning"].includes(m.type())) logs.push(`[console.${m.type()}] ${m.text()}`);
  });
  page.on("pageerror", (e) => logs.push(`[pageerror] ${e.message}`));
  page.on("requestfailed", (r) => logs.push(`[reqfail] ${r.url()} ${r.failure()?.errorText}`));
  page.on("response", async (r) => {
    if (r.status() >= 400) {
      let body = "";
      try { body = (await r.text()).slice(0, 400); } catch (_) {}
      logs.push(`[http ${r.status()}] ${r.url()} :: ${body}`);
    }
  });

  await page.goto(BASE + route, { waitUntil: "networkidle2", timeout: 90000 });
  await new Promise((r) => setTimeout(r, 8000));
  console.log("TITLE:", await page.title());
  console.log("---- CAPTURED ----");
  logs.forEach((l) => console.log(l));
  await browser.close();
})();
