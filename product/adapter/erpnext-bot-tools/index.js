/**
 * ERPNext 机器人工具适配器（BUILD-50，只读）。
 *
 * 与旧 JSH 版 aierp-erp-tools 的相同点（沿用其被验证过的通道约束）：
 *  - 只信任 ctx.messageChannel === "wecom" 且存在 ctx.requesterSenderId 的会话；群聊一律拒绝；
 *  - 模型永远拿不到 ERP 用户身份参数，身份只能是通道给的企微 UserID；
 *  - 所有数值来自 ERP 返回体，适配器只做格式化，禁止模型/适配器自行估算；
 *  - 请求用 HMAC-SHA256 签名（时间戳 + nonce），密钥由环境变量注入。
 *
 * 不同点（避免影响旧 JSH 运行时）：
 *  - 独立的插件 id / 工具名前缀 erp_；独立的 ERP 后端 /api/method/cn_mfg_poc.bot.*；
 *  - 后端用「企微 UserID ↔ ERP User」绑定解析身份，再复用 PC/H5 共用的 cn_mfg_poc.api 业务函数；
 *  - 本文件不引用任何 JSH/ai-erp 旧代码，也不连接旧 MySQL。
 */
import { createHmac, randomBytes } from "node:crypto";

const CHANNEL_ID = "wecom";
const DEFAULT_BASE = "http://127.0.0.1:18000";
const MIN_SECRET_LEN = 32;
const BANNED_SECRET_SNIPPETS = ["change-me", "changeme", "example", "placeholder", "secret"];

/** 与 Python 端 urllib.parse.quote(str, safe="") 严格等价的百分号编码。 */
function enc(v) {
  return encodeURIComponent(String(v)).replace(
    /[!'()*]/g,
    (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase(),
  );
}

function canonical(method, path, ts, nonce, params) {
  const body = Object.keys(params)
    .sort()
    .map((k) => `${enc(k)}=${enc(params[k])}`)
    .join("&");
  return [method, path, String(ts), String(nonce), body].join("\n");
}

function adapterSecret() {
  const secret = (process.env.ERP_BOT_ADAPTER_SECRET || "").trim();
  if (!secret) throw new Error("ERP_BOT_ADAPTER_SECRET 未配置（适配器环境变量）");
  if (secret.length < MIN_SECRET_LEN) throw new Error(`ERP_BOT_ADAPTER_SECRET 过短（至少 ${MIN_SECRET_LEN} 位）`);
  const lower = secret.toLowerCase();
  if (BANNED_SECRET_SNIPPETS.some((b) => lower.includes(b)) || lower === "secret" || lower === "default") {
    throw new Error("ERP_BOT_ADAPTER_SECRET 是占位值，请更换为高熵随机串");
  }
  return secret;
}

function erpBase() {
  return (process.env.ERP_BOT_BASE_URL || DEFAULT_BASE).replace(/\/$/, "");
}

function gatewayAuth() {
  const key = (process.env.ERP_BOT_API_KEY || "").trim();
  const secret = (process.env.ERP_BOT_API_SECRET || "").trim();
  if (!key || !secret) throw new Error("ERP_BOT_API_KEY / ERP_BOT_API_SECRET 未配置（bot-gateway 技术账号 Token）");
  return `token ${key}:${secret}`;
}

/** 通道可信身份：只有企微私聊才放行，绝不接受提示词自报身份。 */
function trustedWecomUserId(ctx) {
  const channel = String(ctx?.messageChannel || ctx?.channelId || "").toLowerCase();
  if (channel !== CHANNEL_ID) return null;
  const id = String(ctx?.requesterSenderId || ctx?.senderId || "").trim();
  return id || null;
}

function isWecomGroupChat(ctx) {
  const candidates = [ctx?.chatType, ctx?.deliveryContext?.chatType]
    .filter((v) => v != null)
    .map((v) => String(v).toLowerCase());
  for (const ct of candidates) {
    if (ct === "group" || ct === "channel") return true;
    if (ct === "direct" || ct === "dm" || ct === "single" || ct === "private") return false;
  }
  const hay = [ctx?.sessionKey, ctx?.nativeChannelId, ctx?.groupId]
    .filter((v) => v != null)
    .map((v) => String(v).toLowerCase())
    .join("|");
  return /(?:^|[|:/])group(?:[|:/]|$)/.test(hay) || /(?:^|[|:/])channel(?:[|:/]|$)/.test(hay);
}

async function signedPost(tool, params, { secretOverride } = {}) {
  const secret = secretOverride || adapterSecret();
  const path = `/api/method/cn_mfg_poc.bot.${tool}`;
  const ts = String(Math.floor(Date.now() / 1000));
  const nonce = randomBytes(12).toString("hex");
  const signature = createHmac("sha256", secret)
    .update(canonical("POST", path, ts, nonce, params), "utf8")
    .digest("hex");
  const res = await fetch(`${erpBase()}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
      Authorization: gatewayAuth(),
      "X-Cn-Bot-Timestamp": ts,
      "X-Cn-Bot-Nonce": nonce,
      "X-Cn-Bot-Signature": signature,
    },
    body: new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)]),
    ).toString(),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new Error(`ERPNext 返回非 JSON（HTTP ${res.status}）：${text.slice(0, 200)}`);
  }
  // Frappe 业务异常走 HTTP 异常体；正常调用体在 message 里
  return json?.message ?? json;
}

function toolResult(ok, text, details) {
  return {
    content: [{ type: "text", text }],
    details: { ok, summary: text, nature: details?.nature || (ok ? "REAL_ERP" : "ERROR"), ...(details || {}) },
  };
}

const money = (v) => (v == null ? "-" : `¥${Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`);
const pct = (v) => `${Math.round(Number(v || 0))}%`;

// ---------------------------------------------------------------- 结果格式化（中文话术）

const FORMATTERS = {
  whoami(d) {
    const emp = d?.employee?.employee_name ? `，员工 ${d.employee.employee_name}` : "";
    return `已绑定 ERP 账号 ${d.erp_user}（${d.full_name || ""}${emp}）\n角色：${(d.roles || []).join("、")}`;
  },
  stock_query(d) {
    if (d?.ambiguous) {
      return `匹配到多个物料，请用编码再问一次：\n${(d.candidates || [])
        .map((c) => `- ${c.item_name}（${c.item_code}）`)
        .join("\n")}`;
    }
    const rows = d?.rows || [];
    if (!rows.length) return `未查到库存记录${d?.item ? `（${d.item}）` : ""}。`;
    const lines = rows.map(
      (r) => `- ${r.item_name}（${r.item_code}）@ ${r.warehouse}：${r.qty} ${r.uom || ""}`,
    );
    return `ERPNext 实时库存：\n${lines.join("\n")}\n共 ${rows.length} 行，数据来自 ERP，非模型估算。`;
  },
  my_orders(d) {
    const rows = d?.orders || [];
    if (!rows.length) return "您名下暂无销售订单。";
    const lines = rows.map(
      (o) => `- ${o.name} ${o.customer} ${money(o.grand_total)} · 交付 ${pct(o.per_delivered)} · ${o.progress}`,
    );
    return `我的销售订单（${rows.length} 张）：\n${lines.join("\n")}`;
  },
  order_progress(d) {
    if (!d?.sales_order) return "未找到该订单。";
    const dn = (d.delivery_notes || []).map((x) => x.name).join("、") || "暂无";
    const inv = (d.invoices || []).map((x) => x.name).join("、") || "暂无";
    return [
      `${d.sales_order}（${d.customer}）`,
      `状态：${d.status} · 金额 ${money(d.grand_total)}`,
      `交付 ${pct(d.per_delivered)} / 收款 ${pct(d.per_billed)} — ${d.progress}`,
      `出库单：${dn}`,
      `发票：${inv}`,
    ].join("\n");
  },
  my_jobs(d) {
    const rows = d?.jobs || [];
    if (!rows.length) return "当前没有分配给您的车间任务。";
    const who = d?.employee_name ? `${d.employee_name}的车间任务` : "我的车间任务";
    const lines = rows.map(
      (j) =>
        `- ${j.name} ${j.operation || ""} · ${j.production_item || ""} 已完成 ${j.total_completed_qty || 0}/${j.for_quantity || 0}（待完成 ${j.pending_qty}）· ${j.status}`,
    );
    return `${who}（${rows.length} 张）：\n${lines.join("\n")}`;
  },
  mgmt_summary(d) {
    if (!d?.company) return "暂无经营数据。";
    const wo = Object.entries(d.work_orders || {})
      .map(([k, v]) => `${k} ${v}`)
      .join("、");
    return [
      `经营摘要（${d.from_date} ~ ${d.to_date}，${d.company}）`,
      `- 销售订单：${d.sales_orders.count} 张 / ${money(d.sales_orders.amount)}`,
      `- 待交付：${d.pending_delivery.count} 张 / ${money(d.pending_delivery.amount)}`,
      `- 生产工单：${wo || "无"}`,
      `- 库存：数量 ${d.stock.qty} / 价值 ${money(d.stock.value)}`,
      "以上为 ERPNext 服务端聚合，非模型估算。",
    ].join("\n");
  },
};

const TOOLS = [
  {
    name: "erp_whoami",
    erp: "whoami",
    description: "查询当前企微身份绑定的 ERPNext 账号、姓名与角色（只读）。只能用于回答「我是谁/我的账号是什么」，不要据此推断权限外的业务数据。",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    build: () => ({}),
  },
  {
    name: "erp_stock_query",
    erp: "stock_query",
    description: "查询 ERPNext 有权仓库的物料实时库存。可用物料中文名关键字或编码，也可指定仓库。用户说「传感器还有多少库存」时用本工具。只读。",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "物料中文名或编码关键字，如 传感器 / SENSOR" },
        warehouse: { type: "string", description: "仓库名称（可选），如 原材料仓 - QC" },
      },
      additionalProperties: false,
    },
    build: (p) => ({ query: p.query || "", warehouse: p.warehouse || "" }),
  },
  {
    name: "erp_my_orders",
    erp: "my_orders",
    description: "查询当前用户可见的销售订单及交付/收款进度。只读。",
    parameters: {
      type: "object",
      properties: { limit: { type: "number", description: "返回条数，默认 10" } },
      additionalProperties: false,
    },
    build: (p) => ({ limit: p.limit || 10 }),
  },
  {
    name: "erp_order_progress",
    erp: "order_progress",
    description: "查询某个销售订单到哪一步：状态、交付百分比、收款百分比、出库单与发票。用户问「这个订单到哪一步」时用。不给单号时返回本人最近一张订单。只读。",
    parameters: {
      type: "object",
      properties: { order: { type: "string", description: "销售订单号，如 SAL-ORD-2026-00005" } },
      additionalProperties: false,
    },
    build: (p) => ({ order: p.order || "" }),
  },
  {
    name: "erp_my_jobs",
    erp: "my_jobs",
    description: "查询当前用户（须绑定在职员工）被指派的车间任务 Job Card 与待完成数量。用户问「我今天有什么任务」时用。只读。",
    parameters: {
      type: "object",
      properties: { limit: { type: "number", description: "返回条数，默认 20" } },
      additionalProperties: false,
    },
    build: (p) => ({ limit: p.limit || 20 }),
  },
  {
    name: "erp_mgmt_summary",
    erp: "mgmt_summary",
    description: "简要经营数据：近 N 天销售订单、待交付、生产工单状态、库存量与价值。仅管理类角色可用，无权限时 ERP 会直接拒绝。只读。",
    parameters: {
      type: "object",
      properties: { days: { type: "number", description: "统计天数，默认 30，最大 365" } },
      additionalProperties: false,
    },
    build: (p) => ({ days: p.days || 30 }),
  },
];

function registerErpTools(api) {
  for (const def of TOOLS) {
    api.registerTool(
      (ctx) => ({
        name: def.name,
        description: def.description,
        parameters: def.parameters,
        async execute(_id, params) {
          const wecomUserId = trustedWecomUserId(ctx);
          if (!wecomUserId) {
            return toolResult(
              false,
              "当前会话没有可信的企业微信发送者身份，无法执行 ERP 工具。请在企微私聊中操作。",
              { reason: "NO_TRUSTED_WECOM_SENDER", messageChannel: ctx?.messageChannel || null },
            );
          }
          if (isWecomGroupChat(ctx)) {
            return toolResult(false, "ERP 工具仅支持企微私聊，请勿在群聊中查询业务数据。", {
              reason: "WECOM_GROUP_NOT_ALLOWED",
              chatType: ctx?.chatType || null,
            });
          }
          try {
            const payload = { wecom_userid: wecomUserId, ...def.build(params || {}) };
            const envelope = await signedPost(def.erp, payload);
            if (!envelope || envelope.ok !== true) {
              const msg = envelope?.message || "ERP 未返回数据";
              const code = envelope?.code || "ERP_REFUSED";
              const friendly =
                code === "PERMISSION_DENIED"
                  ? `您当前的 ERP 角色无权查看该数据（${msg}）`
                  : code === "NOT_BOUND"
                    ? `您的企微账号还没有绑定 ERP 账号（${msg}）`
                    : code === "BAD_SIGNATURE"
                      ? `机器人通道签名校验未通过，已拒绝本次查询（${msg}）`
                      : `ERP 拒绝了这次查询：${msg}`;
              return toolResult(false, friendly, {
                reason: code,
                tool: def.name,
                erpUser: envelope?.erp_user || null,
                nature: "REAL_ERP",
              });
            }
            const text = FORMATTERS[def.erp](envelope.data || {});
            return toolResult(true, text, {
              tool: def.name,
              erpUser: envelope.erp_user,
              wecomUserId: envelope.wecom_userid,
              asOf: envelope.as_of,
              data: envelope.data,
              nature: envelope.nature || "REAL_ERP",
            });
          } catch (err) {
            return toolResult(false, `ERP 查询失败：${String(err?.message || err).slice(0, 200)}`, {
              reason: "ERP_ADAPTER_ERROR",
              tool: def.name,
            });
          }
        },
      }),
      { name: def.name },
    );
  }
}

const plugin = {
  id: "erpnext-bot-tools",
  name: "ERPNext Bot Tools",
  description:
    "WeCom trusted-identity ERPNext read-only tools (stock / orders / order progress / shop-floor jobs / management summary)",
  configSchema: {
    safeParse(value) {
      return { success: true, data: value ?? {} };
    },
  },
  register(api) {
    registerErpTools(api);
  },
};

export default plugin;
export { canonical, enc, signedPost, trustedWecomUserId, isWecomGroupChat, TOOLS, FORMATTERS };
