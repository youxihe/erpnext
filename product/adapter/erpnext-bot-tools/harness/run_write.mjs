/**
 * BUILD-60 本地联调宿主：模拟企微私聊中的「发文件 / 回复确认口令 / 回复取消」，
 * 驱动真实插件代码（工具实现 + before_dispatch 确认拦截 + HMAC 签名 + ERP 调用）。
 *
 * 关键约定：确认与取消**不是工具**，模型无法调用；只有用户本人消息命中口令才会过账。
 *
 * 用法：node harness/run_write.mjs   （样本文件目录 D:/ERP/poc/share/build60）
 */
import { readFileSync } from "node:fs";
import plugin, { TOOLS } from "../index.js";

const ENV_FILE = process.env.ERP_BOT_ENV_FILE || "D:/ERP/poc/share/bot_adapter.local.json";
const FILES = process.env.ERP_BOT_FILES || "D:/ERP/poc/share/build60";

function loadEnv() {
  if (process.env.ERP_BOT_ADAPTER_SECRET && process.env.ERP_BOT_API_KEY) return;
  const cfg = JSON.parse(readFileSync(ENV_FILE, "utf8"));
  process.env.ERP_BOT_ADAPTER_SECRET = cfg.bot_adapter_secret;
  process.env.ERP_BOT_API_KEY = cfg.api_key;
  process.env.ERP_BOT_API_SECRET = cfg.api_secret;
  process.env.ERP_BOT_BASE_URL = cfg.base || "http://127.0.0.1:18000";
}

function session(sender, extra = {}) {
  const ctx = {
    messageChannel: "wecom",
    channelId: "wecom",
    chatType: "direct",
    requesterSenderId: sender,
    senderId: sender,
    sessionKey: `wecom:dm:${sender}`,
    ...extra,
  };
  const tools = new Map();
  const hooks = new Map();
  const api = {
    registerTool(factory) {
      const tool = typeof factory === "function" ? factory(ctx) : factory;
      tools.set(tool.name, tool);
    },
    on(event, handler) {
      if (!hooks.has(event)) hooks.set(event, []);
      hooks.get(event).push(handler);
    },
    config: {},
  };
  return {
    ctx,
    api,
    async invoke(name, params = {}) {
      const tool = tools.get(name);
      if (!tool) throw new Error(`未注册工具 ${name}`);
      return tool.execute(`call-${Date.now()}`, params);
    },
    async say(text, eventExtra = {}) {
      for (const h of hooks.get("before_dispatch") || []) {
        const r = await h({ content: text, senderId: sender, ...eventExtra }, ctx);
        if (r && r.handled) return r;
      }
      return { handled: false, text };
    },
    async sendFile(path) {
      for (const h of hooks.get("before_dispatch") || []) {
        const r = await h({ content: "<media:document>", senderId: sender, mediaPaths: [path] }, ctx);
        if (r && r.handled) return r;
      }
      return { handled: false, text: "" };
    },
  };
}

const results = [];
let failed = 0;

function check(tag, cond, detail = "") {
  const ok = !!cond;
  if (!ok) failed += 1;
  const line = `[${ok ? "PASS" : "FAIL"}] ${tag}${detail ? " · " + detail : ""}`;
  results.push(line);
  console.log(line);
}

async function open(sender, extra) {
  const s = session(sender, extra);
  await plugin.register(s.api);
  return s;
}

async function stockOf(sender, item) {
  const s = await open(sender);
  const r = await s.invoke("erp_stock_query", { query: item });
  const rows = r.details?.data?.rows || [];
  return rows.reduce((sum, x) => sum + (x.qty || 0), 0);
}

async function main() {
  loadEnv();
  console.log(`ERPNext Bot 写入链路本地联调 · ${new Date().toISOString()}`);
  console.log(`BASE=${process.env.ERP_BOT_BASE_URL} · 工具 ${TOOLS.length} 个（其中写操作仅提供预览/草稿，确认不是工具）\n`);

  const zhang = await open("zhangsan"); // 张工：Stock Manager
  const wang = await open("wangming-wx"); // 王明：Sales
  const li = await open("ligong"); // 李工：Manufacturing

  // ---- 1. 模板
  let r = await zhang.invoke("erp_purchase_excel_template");
  console.log(`  张工·要模板 →\n${r.content[0].text}\n`);
  check("W1 生成采购入库 Excel 模板", r.details.ok && /\.xlsx/.test(r.content[0].text));

  // ---- 2. 有效文件 → 预览草稿（库存不变）
  const before1 = await stockOf("zhangsan", "SENSOR");
  r = await zhang.invoke("erp_purchase_excel_preview", { file_path: `${FILES}/采购入库-有效.xlsx` });
  console.log(`  张工·发有效文件 →\n${r.content[0].text}\n`);
  const draftOk = r.details?.data?.ok_preview;
  const draft = r.details?.data?.draft;
  check("W2 有效 Excel 生成待确认草稿", draftOk && /^PID-/.test(draft || ""), `draft=${draft}`);
  const after1 = await stockOf("zhangsan", "SENSOR");
  check("W3 预览阶段库存不变", before1 === after1, `${before1} → ${after1}`);

  // ---- 3. 同一文件重发 → 幂等，不重复建草稿
  r = await zhang.invoke("erp_purchase_excel_preview", { file_path: `${FILES}/采购入库-有效.xlsx` });
  check("W4 同一文件重发返回同一草稿（幂等）",
    r.details?.data?.replayed === true && r.details?.data?.draft === draft,
    `replayed=${r.details?.data?.replayed} draft=${r.details?.data?.draft}`);

  // ---- 4. 本人确认 → 生成采购入库单，库存 +5
  const res = await zhang.say(`确认采购 ${draft}`);
  console.log(`  张工·回复「确认采购 ${draft}」→\n${res.text}\n`);
  const pr = /MAT-PRE-[\d-]+/.exec(res.text || "")?.[0];
  check("W5 确认后生成正式采购入库单", res.handled && !!pr, `PR=${pr || "-"}`);
  const after2 = await stockOf("zhangsan", "SENSOR");
  check("W6 库存按单据增加一次（+5）", Math.abs(after2 - before1 - 5) < 1e-6, `${before1} → ${after2}`);

  // ---- 5. 重复确认 → 不重复入库
  const res2 = await zhang.say(`确认采购 ${draft}`);
  console.log(`  张工·重复确认 →\n${res2.text}\n`);
  const after3 = await stockOf("zhangsan", "SENSOR");
  check("W7 重复确认不重复入库", /已确认过|未重复/.test(res2.text || "") && after3 === after2, `${after2} → ${after3}`);

  // ---- 6. 无效文件（错误编码 / 负数量 / 无表头 / 无效供应商 / 无效仓库）
  for (const [file, tag] of [
    ["采购入库-无效编码.xlsx", "W8a 物料不存在被拒"],
    ["采购入库-数量为负.xlsx", "W8b 数量为负被拒"],
    ["采购入库-无表头.xlsx", "W8c 无表头被拒"],
    ["采购入库-供应商无效.xlsx", "W8d 供应商无效被拒"],
    ["采购入库-仓库无效.xlsx", "W8e 非本公司/组仓库被拒"],
  ]) {
    const rr = await zhang.invoke("erp_purchase_excel_preview", { file_path: `${FILES}/${file}` });
    check(tag, rr.details?.data?.ok_preview === false, (rr.content[0].text || "").split("\n")[1] || "");
  }

  // ---- 7. 取消草稿 → 库存不变
  const beforeCancel = await stockOf("zhangsan", "FASTENER");
  r = await zhang.invoke("erp_purchase_excel_preview", { file_path: `${FILES}/采购入库-取消.xlsx` });
  const draft2 = r.details?.data?.draft;
  const cancelRes = await zhang.say(`取消采购 ${draft2}`);
  console.log(`  张工·取消草稿 ${draft2} →\n${cancelRes.text}\n`);
  const afterCancel = await stockOf("zhangsan", "FASTENER");
  check("W9 取消草稿不扣库也不入库", /已取消/.test(cancelRes.text || "") && beforeCancel === afterCancel,
    `${beforeCancel} → ${afterCancel}`);

  // ---- 8. 无仓储角色：王明预览采购 Excel 被拒
  r = await wang.invoke("erp_purchase_excel_preview", { file_path: `${FILES}/采购入库-有效.xlsx` });
  check("W10 无采购/仓储角色被拒", !r.details.ok && r.details.reason === "PERMISSION_DENIED",
    (r.content[0].text || "").slice(0, 60));

  // ---- 9. 客户报备：预览 → 确认 → Lead
  const cust = `苏州新元精密机械有限公司`;
  r = await wang.invoke("erp_customer_report_prepare", { customer_name: cust, contact_name: "周经理", mobile_no: "13700005555" });
  console.log(`  王明·报备客户 →\n${r.content[0].text}\n`);
  const bd = r.details?.data?.draft;
  check("W11 客户报备生成待确认草稿", !!bd && /^BD-/.test(bd), `draft=${bd}`);

  const cRes = await wang.say(`确认报备 ${bd}`);
  console.log(`  王明·回复「确认报备 ${bd}」→\n${cRes.text}\n`);
  const lead = /CRM-LEAD-[\d-]+/.exec(cRes.text || "")?.[0];
  check("W12 确认后生成正式报备单(Lead)", cRes.handled && !!lead, `lead=${lead || "-"}`);

  const cRes2 = await wang.say(`确认报备 ${bd}`);
  check("W13 报备重复确认不重复创建", /已确认过|未重复/.test(cRes2.text || ""), (cRes2.text || "").split("\n")[0]);

  r = await wang.invoke("erp_customer_report_prepare", { customer_name: cust });
  check("W14 同名客户再次报备提示已存在", r.details?.data?.ok_preview === false,
    r.details?.data?.hint || "");

  // ---- 10. 李工（无销售角色）报备被拒
  r = await li.invoke("erp_customer_report_prepare", { customer_name: "随便一家新公司有限公司" });
  check("W15 无销售角色报备被拒", !r.details.ok && r.details.reason === "PERMISSION_DENIED",
    (r.content[0].text || "").slice(0, 60));

  // ---- 11. 群聊里发确认口令不生效
  const group = await open("zhangsan", { chatType: "group", sessionKey: "wecom:group:9" });
  const gRes = await group.say(`确认采购 ${draft}`);
  check("W16 群聊中的确认口令不被处理", gRes.handled !== true);

  console.log(`\n合计 ${results.length} 项，失败 ${failed} 项`);
  process.exit(failed ? 1 : 0);
}

main().catch((err) => {
  console.error(`宿主异常：${err.stack || err.message}`);
  process.exit(2);
});
