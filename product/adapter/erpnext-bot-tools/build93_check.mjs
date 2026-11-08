// BUILD-93：机器人适配器离线校验（不需要真实企微）。
// 用服务端真实返回的样本，验证三个新工具已注册、且话术把「任务」与「实物入库」分列。
import fs from "node:fs";
import { TOOLS, FORMATTERS } from "./index.js";

const SAMPLES = process.env.BUILD93_SAMPLES || "/hostshare/bot93-samples.json";
const OUT = process.env.BUILD93_OUT || "/hostshare/build93-adapter.json";
const samples = JSON.parse(fs.readFileSync(SAMPLES, "utf8"));
const results = [];
const check = (name, ok, detail = "") => {
  results.push({ name, ok: !!ok, detail: String(detail).slice(0, 300) });
  console.log(`${ok ? "PASS" : "FAIL"} ${name} | ${String(detail).slice(0, 200)}`);
};

const want = ["erp_order_execution", "erp_my_production_tasks", "erp_materials_shortage"];
for (const name of want) {
  const def = TOOLS.find((t) => t.name === name);
  check(`工具已注册 ${name}`, !!def && def.module === "cn_mfg_poc.bot" && !!def.build,
    def ? `module=${def.module} erp=${def.erp}` : "未找到");
}

const o = samples.order_execution.data;
const txt = FORMATTERS.order_execution(o);
check("订单话术含订单号与交期", txt.includes(o.sales_order) && txt.includes("承诺交期"), txt.split("\n")[0]);
check("订单话术把任务数与实物入库分列",
  /固定任务：共 \d+ 项/.test(txt) && /【原生实物】完工入库/.test(txt), txt.split("\n")[2]);
check("订单话术强调任务不等于入库",
  txt.includes("任务状态只反映过程") && txt.includes("唯一凭据"), txt.split("\n").slice(-1)[0]);

const t = samples.my_production_tasks.data;
const ttxt = FORMATTERS.my_production_tasks(t);
check("任务话术列出本人任务与临期/逾期",
  ttxt.includes("我的生产任务") && ttxt.includes("逾期") && ttxt.includes("临期"),
  ttxt.split("\n")[0]);

const s = samples.materials_shortage.data;
const stxt = FORMATTERS.materials_shortage(s);
check("缺料话术给出订单/物料/数量",
  s.count > 0 ? stxt.includes(s.orders[0].sales_order) && stxt.includes("缺") : stxt.includes("没有"),
  stxt.split("\n").slice(0, 2).join(" "));

const passed = results.filter((r) => r.ok).length;
console.log(`RESULT ${passed}/${results.length}`);
fs.writeFileSync(
  OUT,
  JSON.stringify({ summary: { passed, total: results.length }, steps: results, samples: {
    order_execution: txt, my_production_tasks: ttxt, materials_shortage: stxt } }, null, 1),
);
