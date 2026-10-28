/**
 * BUILD-50 本地联调宿主：在没有真实企业微信时，模拟 OpenClaw 的插件 API 与消息会话，
 * 直接驱动 product/adapter/erpnext-bot-tools/index.js 的真实代码路径（工具实现、身份校验、
 * HMAC 签名、ERP 调用全部是真实执行；只有「企微消息信封」是注入的）。
 *
 * 用法：
 *   node harness/run.mjs            # 读 D:/ERP/poc/share/bot_adapter.local.json
 *   ERP_BOT_ADAPTER_SECRET=... ERP_BOT_API_KEY=... ERP_BOT_API_SECRET=... node harness/run.mjs
 *
 * 任一断言失败 → exit 1。
 */
import { readFileSync } from "node:fs";
import plugin, { TOOLS } from "../index.js";

const ENV_FILE = process.env.ERP_BOT_ENV_FILE || "D:/ERP/poc/share/bot_adapter.local.json";

function loadEnv() {
  if (process.env.ERP_BOT_ADAPTER_SECRET && process.env.ERP_BOT_API_KEY) return;
  try {
    const cfg = JSON.parse(readFileSync(ENV_FILE, "utf8"));
    process.env.ERP_BOT_ADAPTER_SECRET = cfg.bot_adapter_secret;
    process.env.ERP_BOT_API_KEY = cfg.api_key;
    process.env.ERP_BOT_API_SECRET = cfg.api_secret;
    process.env.ERP_BOT_BASE_URL = cfg.base || "http://127.0.0.1:18000";
  } catch (err) {
    console.error(`无法读取适配器本地配置 ${ENV_FILE}：${err.message}`);
    process.exit(2);
  }
}

/** 极简 OpenClaw api 模拟：registerTool(factory(ctx), {name}) + 按名调用。 */
function mockApi(ctx) {
  const tools = new Map();
  return {
    tools,
    registerTool(factory) {
      const tool = typeof factory === "function" ? factory(ctx) : factory;
      tools.set(tool.name, tool);
    },
    on() {},
    config: {},
    async invoke(name, params = {}) {
      const tool = tools.get(name);
      if (!tool) throw new Error(`未注册工具 ${name}`);
      return tool.execute(`call-${Date.now()}`, params);
    },
  };
}

const results = [];
let failed = 0;

function check(tag, cond, detail) {
  const ok = !!cond;
  if (!ok) failed += 1;
  const line = `[${ok ? "PASS" : "FAIL"}] ${tag}${detail ? " · " + detail : ""}`;
  results.push(line);
  console.log(line);
}

let GOOD_SECRET = "";

async function run(ctx, tool, params = {}, { secretOverride } = {}) {
  const api = mockApi(ctx);
  await plugin.register(api);
  if (secretOverride) process.env.ERP_BOT_ADAPTER_SECRET = secretOverride;
  const res = await api.invoke(tool, params);
  if (secretOverride) process.env.ERP_BOT_ADAPTER_SECRET = GOOD_SECRET;
  return res;
}

const dm = (sender) => ({
  messageChannel: "wecom",
  channelId: "wecom",
  chatType: "direct",
  requesterSenderId: sender,
  senderId: sender,
  sessionKey: `wecom:dm:${sender}`,
});

async function main() {
  loadEnv();
  GOOD_SECRET = process.env.ERP_BOT_ADAPTER_SECRET;
  console.log(`ERPNext Bot 适配器本地联调 · ${new Date().toISOString()}`);
  console.log(`BASE=${process.env.ERP_BOT_BASE_URL || "http://127.0.0.1:18000"} · 工具数 ${TOOLS.length}\n`);

  // ---- 1. 李工（制造用户）：车间任务 + 库存允许，销售订单/经营摘要拒绝
  let r = await run(dm("ligong"), "erp_my_jobs");
  console.log(`  李工·我的任务 →\n${r.content[0].text}\n`);
  check("T1 李工 我的车间任务 返回真实数据", r.details.ok && (r.details.data?.jobs?.length ?? 0) > 0,
    `jobs=${r.details.data?.jobs?.length ?? 0} employee=${r.details.data?.employee_name ?? "-"}`);

  r = await run(dm("ligong"), "erp_stock_query", { query: "传感器" });
  console.log(`  李工·库存 →\n${r.content[0].text}\n`);
  check("T2 李工 库存查询命中「传感器」", r.details.ok && /传感器/.test(r.content[0].text),
    `rows=${r.details.data?.rows?.length ?? 0}`);

  r = await run(dm("ligong"), "erp_my_orders");
  check("T3 李工 销售订单被拒（无销售角色）", !r.details.ok && r.details.reason === "PERMISSION_DENIED",
    r.content[0].text.slice(0, 60));

  r = await run(dm("ligong"), "erp_mgmt_summary");
  check("T4 李工 经营摘要被拒（非管理角色）", !r.details.ok && r.details.reason === "PERMISSION_DENIED",
    r.content[0].text.slice(0, 60));

  // ---- 2. 王明（销售）：我的订单 + 订单进度允许，车间任务拒绝
  r = await run(dm("wangming-wx"), "erp_my_orders");
  console.log(`  王明·我的订单 →\n${r.content[0].text}\n`);
  check("T5 王明 我的销售订单可见", r.details.ok && /SAL-ORD-/.test(r.content[0].text),
    `orders=${r.details.data?.orders?.length ?? 0}`);

  r = await run(dm("wangming-wx"), "erp_order_progress", { order: "SAL-ORD-2026-00005" });
  console.log(`  王明·订单进度 →\n${r.content[0].text}\n`);
  check("T6 王明 订单进度返回真实状态", r.details.ok && /SAL-ORD-2026-00005/.test(r.content[0].text),
    r.content[0].text.split("\n")[1] || "");

  r = await run(dm("wangming-wx"), "erp_my_jobs");
  check("T7 王明 车间任务被拒（非制造角色/无员工）", !r.details.ok && r.details.reason === "PERMISSION_DENIED",
    r.content[0].text.slice(0, 60));

  // ---- 3. 张工（仓库主管）：库存 + 经营摘要允许
  r = await run(dm("zhangsan"), "erp_stock_query", { query: "SENSOR" });
  console.log(`  张工·库存(SENSOR) →\n${r.content[0].text}\n`);
  check("T8 张工 库存查询命中 SENSOR", r.details.ok && /SENSOR/.test(r.content[0].text),
    `rows=${r.details.data?.rows?.length ?? 0}`);

  r = await run(dm("zhangsan"), "erp_stock_query", { query: "SENSOR", warehouse: "贸易品仓 - QC" });
  check("T8b 张工 无库存的仓库返回空而不是报错", r.details.ok && (r.details.data?.rows?.length ?? 0) === 0,
    r.content[0].text.slice(0, 40));

  r = await run(dm("zhangsan"), "erp_mgmt_summary", { days: 30 });
  console.log(`  张工·经营摘要 →\n${r.content[0].text}\n`);
  check("T9 张工 经营摘要（Stock Manager）", r.details.ok && /经营摘要/.test(r.content[0].text));

  // ---- 4. 赵经理（系统管理员）
  r = await run(dm("zhaojingli"), "erp_whoami");
  console.log(`  赵经理·我是谁 →\n${r.content[0].text}\n`);
  check("T10 赵经理 whoami 绑定解析正确", r.details.ok && /zhaojingli@/.test(r.content[0].text),
    r.details.erpUser || "");

  // ---- 5. 通道与身份负例
  r = await run(dm("weixiubao"), "erp_whoami");
  check("T11 未绑定企微账号被拒", !r.details.ok && r.details.reason === "NOT_BOUND",
    r.content[0].text.slice(0, 60));

  r = await run({ ...dm("ligong"), chatType: "group", sessionKey: "wecom:group:1" }, "erp_stock_query", { query: "传感器" });
  check("T12 群聊拒绝（不下发 ERP）", !r.details.ok && r.details.reason === "WECOM_GROUP_NOT_ALLOWED",
    r.content[0].text.slice(0, 40));

  r = await run({ messageChannel: "web", requesterSenderId: "ligong" }, "erp_stock_query", {});
  check("T13 非企微通道拒绝", !r.details.ok && r.details.reason === "NO_TRUSTED_WECOM_SENDER",
    r.content[0].text.slice(0, 40));

  r = await run(dm("ligong"), "erp_stock_query", { query: "传感器" }, { secretOverride: "x".repeat(48) });
  check("T14 篡改签名被拒（BAD_SIGNATURE）", !r.details.ok && r.details.reason === "BAD_SIGNATURE",
    r.content[0].text.slice(0, 60));

  // ---- 6. 三入口一致性：同一订单在 Bot 与 ERP 侧数值一致（由 python 侧 build50_verify.py 复核）
  r = await run(dm("wangming-wx"), "erp_order_progress", { order: "SAL-ORD-2026-00005" });
  const so = r.details.data;
  check("T15 订单进度字段完整（状态/交付/收款）",
    !!so && so.status === "To Deliver and Bill" && so.per_delivered === 0,
    `status=${so?.status} delivered=${so?.per_delivered} billed=${so?.per_billed}`);

  console.log(`\n合计 ${results.length} 项，失败 ${failed} 项`);
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  console.error(`宿主异常：${err.stack || err.message}`);
  process.exit(2);
});
