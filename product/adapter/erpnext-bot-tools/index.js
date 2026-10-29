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
import { createHmac, randomBytes, createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";

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

function mediaDir() {
  const dir = process.env.ERP_BOT_MEDIA_DIR || join(process.cwd(), "tmp-media");
  mkdirSync(dir, { recursive: true });
  return dir;
}

function writeMediaFile(fileName, base64) {
  const safe = basename(String(fileName || "template.xlsx")).replace(/[^\w.\u4e00-\u9fff-]+/g, "_");
  const path = join(mediaDir(), `${Date.now()}_${safe}`);
  writeFileSync(path, Buffer.from(base64, "base64"));
  return path;
}

function collectXlsxPaths(event, ctx) {
  const paths = []
    .concat(event?.mediaPaths || [])
    .concat(event?.media?.map?.((m) => m?.path) || [])
    .concat(event?.metadata?.mediaPaths || [])
    .concat(ctx?.mediaPaths || [])
    .filter(Boolean)
    .map((p) => String(p));
  return paths.filter((p) => p.toLowerCase().endsWith(".xlsx"));
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

async function signedPost(module, tool, params, { secretOverride } = {}) {
  const secret = secretOverride || adapterSecret();
  const path = `/api/method/${module}.${tool}`;
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
  purchase_excel_template(d) {
    const path = writeMediaFile(d.file_name, d.file_base64);
    return [
      d.hint || "",
      `模板列：${(d.columns || []).join(" / ")}`,
      `文件已生成：${basename(path)}`,
      "填好后直接把 xlsx 发回本对话，系统会先核对再入库。",
    ]
      .filter(Boolean)
      .join("\n");
  },
  parse_purchase_excel(d) {
    if (!d?.ok_preview) {
      const errs = (d?.errors || []).slice(0, 8).map((e) => `- ${e}`).join("\n");
      return [`文件未通过核对（${d?.error_count ?? 0} 处）：`, errs, d?.hint || ""].filter(Boolean).join("\n");
    }
    const lines = (d.rows || []).map(
      (r) => `- ${r.item_name || r.item_code}（${r.item_code}）：${r.qty} ${r.uom || ""} × ${r.rate ?? "-"}`,
    );
    return [
      `采购入库待确认单 ${d.draft}${d.replayed ? "（该文件此前已生成过草稿，未重复创建）" : ""}`,
      `供应商：${d.supplier} · 入库仓库：${d.warehouse}`,
      ...lines,
      `合计数量 ${d.total_qty} · 参考金额 ¥${Number(d.total_amount || 0).toLocaleString("zh-CN")}`,
      d.stock_hint || "",
      `确认请回复「${d.confirm_phrase}」；不入库请回复「取消采购 ${d.draft}」。`,
    ]
      .filter(Boolean)
      .join("\n");
  },
  prepare_customer_report(d) {
    if (!d?.ok_preview) {
      return d?.hint || "该客户无法报备。";
    }
    return [
      `客户报备待确认单 ${d.draft}${d.replayed ? "（此前已生成过，未重复创建）" : ""}`,
      `- 客户名称：${d.customer_name}`,
      `- 联系人：${d.contact_name || "-"} · 电话：${d.mobile_no || "-"}`,
      d.stock_hint || "",
      `确认请回复「${d.confirm_phrase}」；放弃请回复「取消报备 ${d.draft}」。`,
    ]
      .filter(Boolean)
      .join("\n");
  },
  my_drafts(d) {
    const p = d?.purchase || [];
    const c = d?.customer || [];
    if (!p.length && !c.length) return "当前没有待您确认的草稿。";
    const lines = [
      ...p.map((x) => `- [采购入库] ${x.name} ${x.supplier || ""} → ${x.warehouse || ""}${x.file_name ? ` · ${x.file_name}` : ""}`),
      ...c.map((x) => `- [客户报备] ${x.name} ${x.summary || ""}`),
    ];
    return `待确认草稿（${p.length + c.length}）：\n${lines.join("\n")}\n确认请回复「确认采购 单号」或「确认报备 单号」。`;
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
    module: "cn_mfg_poc.bot",
    erp: "whoami",
    description: "查询当前企微身份绑定的 ERPNext 账号、姓名与角色（只读）。只能用于回答「我是谁/我的账号是什么」，不要据此推断权限外的业务数据。",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    build: () => ({}),
  },
  {
    name: "erp_stock_query",
    module: "cn_mfg_poc.bot",
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
    module: "cn_mfg_poc.bot",
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
    module: "cn_mfg_poc.bot",
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
    module: "cn_mfg_poc.bot",
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
    module: "cn_mfg_poc.bot",
    erp: "mgmt_summary",
    description: "简要经营数据：近 N 天销售订单、待交付、生产工单状态、库存量与价值。仅管理类角色可用，无权限时 ERP 会直接拒绝。只读。",
    parameters: {
      type: "object",
      properties: { days: { type: "number", description: "统计天数，默认 30，最大 365" } },
      additionalProperties: false,
    },
    build: (p) => ({ days: p.days || 30 }),
  },
  // ---------------- BUILD-60：写操作的「预览/草稿」阶段（确认不在工具里，见 registerConfirmDispatch）
  {
    name: "erp_purchase_excel_template",
    module: "cn_mfg_poc.bot_write",
    erp: "purchase_excel_template",
    description: "生成 ERPNext 采购入库 Excel 模板供用户下载填写。只给模板，不做任何写入。",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    build: () => ({}),
  },
  {
    name: "erp_purchase_excel_preview",
    module: "cn_mfg_poc.bot_write",
    erp: "parse_purchase_excel",
    description: "核对用户发回的采购入库 Excel：逐行校验物料/数量/单价/供应商/仓库，生成待确认草稿预览，不改库存。用户发来 xlsx 时用本工具。",
    parameters: {
      type: "object",
      properties: {
        file_path: { type: "string", description: "本地临时文件路径（渠道给的附件路径）" },
        supplier: { type: "string", description: "文件中未填供应商时的补充值（可选）" },
        warehouse: { type: "string", description: "文件中未填仓库时的补充值（可选）" },
      },
      additionalProperties: false,
    },
    build: (p) => ({ supplier: p.supplier || "", warehouse: p.warehouse || "" }),
    fileParam: "file_path",
  },
  {
    name: "erp_customer_report_prepare",
    module: "cn_mfg_poc.bot_write",
    erp: "prepare_customer_report",
    description: "自然语言客户报备：查重后生成待确认报备草稿预览（不写入 ERP）。用户说「报备客户 XXX」时用；确认由用户本人回复口令完成。",
    parameters: {
      type: "object",
      properties: {
        customer_name: { type: "string", description: "客户全称（必填）" },
        contact_name: { type: "string", description: "联系人（可选）" },
        mobile_no: { type: "string", description: "联系电话（可选）" },
        note: { type: "string", description: "备注（可选）" },
      },
      required: ["customer_name"],
      additionalProperties: false,
    },
    build: (p) => ({
      customer_name: p.customer_name || "",
      contact_name: p.contact_name || "",
      mobile_no: p.mobile_no || "",
      note: p.note || "",
      idempotency_key: `cr:${p.customer_name || ""}`.slice(0, 120),
    }),
  },
  {
    name: "erp_my_drafts",
    module: "cn_mfg_poc.bot_write",
    erp: "my_drafts",
    description: "列出当前用户待确认的草稿（采购入库/客户报备）。只读。",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    build: () => ({}),
  },
];

function readIncomingFile(p) {
  const path = String(p || "").trim();
  if (!path) throw new Error("缺少文件路径");
  if (!existsSync(path)) throw new Error("文件还没收到（可能仍在传输），请重新发送一次 .xlsx");
  const buf = readFileSync(path);
  if (buf.length > 2 * 1024 * 1024) throw new Error("文件超过 2MB，请精简后重发");
  return {
    file_name: basename(path),
    file_base64: buf.toString("base64"),
    file_sha256: createHash("sha256").update(buf).digest("hex"),
  };
}

/** 直接调用 ERP 并返回信封（供确认/取消这类「用户本人指令」使用）。 */
async function erpCall(ctx, module, method, params) {
  const wecomUserId = trustedWecomUserId(ctx);
  if (!wecomUserId) return { ok: false, code: "NO_TRUSTED_WECOM_SENDER" };
  if (isWecomGroupChat(ctx)) return { ok: false, code: "WECOM_GROUP_NOT_ALLOWED" };
  return signedPost(module, method, { wecom_userid: wecomUserId, ...params });
}

const CONFIRM_PURCHASE = /^\s*确认\s*采购\s*[：:#＃]?\s*([A-Za-z]{2,}-\d+|\d+)\s*$/;
const CONFIRM_REPORT = /^\s*确认\s*报备\s*[：:#＃]?\s*([A-Za-z]{2,}-\d+|\d+)\s*$/;
const CANCEL_DRAFT = /^\s*取消\s*(采购|报备)\s*[：:#＃]?\s*([A-Za-z]{2,}-\d+|\d+)\s*$/;

function friendlyRefusal(env) {
  const code = env?.code || "ERP_REFUSED";
  const msg = env?.message || "";
  if (code === "PERMISSION_DENIED") return `您当前的 ERP 角色无权执行该操作（${msg}）`;
  if (code === "NOT_BOUND") return `您的企微账号还没有绑定 ERP 账号（${msg}）`;
  if (code === "BAD_SIGNATURE") return `机器人通道签名校验未通过，已拒绝（${msg}）`;
  return `${msg || "ERP 拒绝了本次操作"}`;
}

function formatConfirm(env) {
  if (!env?.ok) return friendlyRefusal(env);
  const d = env.data || {};
  if (d.kind === "PURCHASE") {
    return [
      d.already_confirmed ? "该草稿此前已确认过，未重复入库。" : "✅ 采购入库已过账，库存按单据增加一次。",
      `入库单：${d.purchase_receipt}（docstatus ${d.docstatus}）`,
      d.message || "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (d.existing) return `未创建报备：${d.message}`;
  return [
    d.already_confirmed ? "该报备此前已确认过，未重复创建。" : "✅ 客户报备已写入 ERP，PC 与 H5 立即可见。",
    `报备单：${d.lead}${d.lead_owner ? ` · 负责人 ${d.lead_owner}` : ""}`,
    d.message || "",
  ]
    .filter(Boolean)
    .join("\n");
}

function formatCancel(env) {
  if (!env?.ok) return friendlyRefusal(env);
  const d = env.data || {};
  return `${d.message || `草稿 ${d.draft} 已取消`}\n库存未发生任何变化。`;
}

/**
 * 「确认/取消」必须由用户本人消息触发：走 before_dispatch 拦截，
 * 不注册成工具，模型无法替用户确认（沿用旧 AIERP 的 SOP）。
 */
function registerConfirmDispatch(api) {
  const handler = async (event, ctx) => {
    const channelId = String(ctx?.messageChannel || ctx?.channelId || "").toLowerCase();
    if (channelId !== CHANNEL_ID) return;
    if (event?.isGroup || isWecomGroupChat(ctx)) return;
    const text = String(event?.content || event?.body || "").trim();

    // 附件：xlsx → 自动核对（不入库）
    const paths = collectXlsxPaths(event, ctx);
    if (paths.length) {
      const wecomUserId = trustedWecomUserId(ctx);
      if (!wecomUserId) return { handled: true, text: "当前会话没有可信的企微身份，无法核对文件。" };
      try {
        const payload = { wecom_userid: wecomUserId, ...readIncomingFile(paths[0]) };
        const env = await signedPost("cn_mfg_poc.bot_write", "parse_purchase_excel", payload);
        const d = (env && env.data) || {};
        const out = env?.ok ? FORMATTERS.parse_purchase_excel(d) : friendlyRefusal(env);
        return { handled: true, text: out };
      } catch (err) {
        return { handled: true, text: `文件核对失败：${String(err?.message || err).slice(0, 160)}。库存未变化。` };
      }
    }

    let m = CONFIRM_PURCHASE.exec(text);
    if (m) {
      const env = await erpCall(ctx, "cn_mfg_poc.bot_write", "confirm_draft", { kind: "PURCHASE", draft: m[1] });
      return { handled: true, text: formatConfirm(env) };
    }
    m = CONFIRM_REPORT.exec(text);
    if (m) {
      const env = await erpCall(ctx, "cn_mfg_poc.bot_write", "confirm_draft", { kind: "CUSTOMER", draft: m[1] });
      return { handled: true, text: formatConfirm(env) };
    }
    m = CANCEL_DRAFT.exec(text);
    if (m) {
      const kind = m[1] === "采购" ? "PURCHASE" : "CUSTOMER";
      const env = await erpCall(ctx, "cn_mfg_poc.bot_write", "cancel_draft", { kind, draft: m[2] });
      return { handled: true, text: formatCancel(env) };
    }
    return;
  };
  try {
    api.on("before_dispatch", handler, { priority: 50 });
  } catch {
    api.on("before_dispatch", handler);
  }
}

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
            if (def.fileParam) {
              const file = readIncomingFile(params?.[def.fileParam]);
              Object.assign(payload, file);
            }
            const envelope = await signedPost(def.module, def.erp, payload);
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
    registerConfirmDispatch(api);
  },
};

export default plugin;
export { canonical, enc, signedPost, trustedWecomUserId, isWecomGroupChat, TOOLS, FORMATTERS };
