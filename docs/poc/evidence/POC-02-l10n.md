# POC-02 — 简体中文默认界面（证据记录）

执行日期：2026-10-26
状态：**PASS**

---

## 1. 默认语言与区域（系统级）

来源必须是实际 Language 表，POC-00/01 已确认：

```
$ 查询 Language 表 → name=zh, language_code=zh, language_name=中文
                    name=zh-TW
  结论：本版本语言代码是 zh，不存在 zh-CN
```

System Settings（Setup Wizard 由 `bench execute` 官方入口完成）实测：

| 字段 | 值 |
|---|---|
| language | `zh` |
| country | `China` |
| time_zone | `Asia/Shanghai` |
| currency | `CNY` |
| date_format | `yyyy-mm-dd` |
| number_format | `#,###.##` |
| enable_scheduler | 1 |
| setup_complete | 1 |

Global Defaults：`default_company=昆山启程智能设备有限公司`、`country=China`、`default_currency=CNY`。

## 2. 语言优先级验证（User.language 优先，再回退 System Settings）

7 个测试用户（`poc/scripts/poc-users.py` 幂等创建）全部 `language=""`（未设置）：

```
chengong@ / ligong@ / liugong@ / wangming@ / zhanggong@ / zhaojingli@ / zhoukaiji@  → language=""
Administrator                                                                       → language=null
```

实测结果：

| 场景 | 结果 |
|---|---|
| Administrator（language=null）登录 | 界面中文（回退 System Settings.zh）✓ |
| 新建用户 王明（language=""）登录 | 界面中文 ✓（见 `poc-02-salesorder-list.png`） |
| 全新浏览器会话（新 sid）重新登录 | 仍为中文，标题 `销售订单` ✓（`poc-02-newsession-zh.png`） |
| 手动把王明 language 改成 `en` | 界面立刻变英文 ✓（`poc-02-user-en.png`）→ **个人选择可生效，未被锁死** |
| 改回 `""` 后新会话 | 恢复中文 ✓ |

## 3. 中文翻译编译产物（升级回退风险检查）

```
sites/assets/locale/zh/LC_MESSAGES/
  erpnext.mo  856,663 bytes
  frappe.mo   428,802 bytes
```

`bench build` 输出明确出现 `MO file created at .../locale/zh/LC_MESSAGES/{frappe,erpnext}.mo`，
说明 zh 翻译链路（po → mo → 运行时）完整。`bench migrate` 前后抽查无回退迹象。

> 关于已知的 Frappe 16 zh 翻译回退问题：本轮用「语言代码 + .mo 产物 + 新会话 + 翻译量」四点验证，
> 未观察到回退；若后续升级出现回退，重放 `bench build` + 本 App 补丁即可恢复（见下）。

## 4. 翻译缺口清单（真实存在，未隐瞒）

用 `poc/scripts/check_zh_gaps.py` 扫描 `frappe/locale/zh.po` 与 `erpnext/locale/zh.po`，
POC 关键术语共 8 处 `msgstr` 为空：

| msgid | 现象 | 补齐译文 |
|---|---|---|
| `Item` | 物料列表标题/按钮显示英文 Item | 物料 |
| `No {0} created` | 列表空状态「No 销售订单 created」 | 暂无{0} |
| `Clear the filters to see all records.` | 列表空状态英文提示 | 清除筛选条件以查看全部记录。 |
| `A customer's confirmed order.` | 销售订单空状态英文说明 | 客户确认的销售订单。 |
| `Advance` | 收付款「预付款」相关 | 预付款 |
| `For Quantity` | 工单/领料数量 | 本次数量 |
| `Transfer Material` | 工单领料按钮 | 转移物料 |
| `Work Order Operations` | 工单工序表 | 工单工序 |

### 修复方式（不改上游文件，可重复导入）

- 自定义 App `cn_mfg_poc` 新增 patch `cn_mfg_poc.patches.v0_0_1.zh_translation_overrides`
  （源码在仓库 `poc/apps/cn_mfg_poc/`），幂等写入站点级 `Translation` 记录。
- 依据：`frappe/translate.py get_all_translations()` 中 DB（Translation / user translations）
  **最后合并，优先级高于 app 自带 .po** —— 属于官方支持的覆盖方式。
- 重放方式：`bench --site erpnext-poc.localhost migrate`（幂等，重复执行结果一致）。

### 修复前后对比（同一页面）

| 页面 | 修复前 | 修复后 |
|---|---|---|
| /app/sales-order 空状态 | No 销售订单 created / A customer's confirmed order. | **暂无销售订单 / 客户确认的销售订单。** |
| /app/item | 标题 Item / 没有找到Item / Clear the filters... | **物料 / 没有找到物料 / 清除筛选条件以查看全部记录。** |

## 5. 中文页面证据（3 张以上，`D:\ERP\poc\share\screenshots\`）

| 文件 | 页面 | 说明 |
|---|---|---|
| `poc-01-desk.png` | /app 应用入口 | 搜索栏中文 |
| `poc-01-customer.png` | /app/customer | 销售工作台中文侧栏 + 客户列表 |
| `poc-02-salesorder-list.png` | /app/sales-order（修复前） | 证明缺口真实存在 |
| `poc-02-salesorder-list-after.png` | /app/sales-order（修复后） | 全中文 |
| `poc-02-item-after.png` | /app/item（修复后） | 全中文（库存工作台侧栏） |
| `poc-02-workorder.png` | /app/work-order | 生产工作台：物料清单/生产计划/生产工单/生产任务单/物料移动/委外/工具 |
| `poc-02-bom.png` | /app/bom | 标题「物料清单」 |
| `poc-02-jobcard.png` | /app/job-card | 标题「生产任务单」 |
| `poc-02-stockentry.png` | /app/stock-entry | 标题「物料移动」 |
| `poc-02-user-en.png` | 同用户切英文 | 证明个人语言选择生效、不锁死 |
| `poc-02-newsession-zh.png` | 新会话 | 证明默认语言持久 |

## 6. DocType 中文标题实测（列表页 title）

```
/app/item           → 物料
/app/bom            → 物料清单
/app/work-order     → 生产工单
/app/job-card       → 生产任务单
/app/stock-entry    → 物料移动
/app/purchase-order → 采购订单
/app/warehouse      → 仓库 树
/app/customer       → 客户
/app/sales-order    → 销售订单
```

## 7. 仍存在的英文（不影响 POC 关键流程，记录备查）

- ERPNext / Frappe 内部模块名、部分报表列、部分报错消息仍是英文（上游翻译量限制）。
- POS、HR、资产等本 POC 范围外模块未逐一核对（POC-03 会把它们从普通角色导航隐藏）。
- 搜索框占位符、部分 onboarding 卡片仍有英文残留。

## 8. POC-02 结论

- 系统级默认 zh / China / CNY / Asia/Shanghai / yyyy-mm-dd ✓
- 新用户与全新会话默认中文，登录刷新不回退 ✓
- 个人切换英文生效、不锁死 ✓
- 8 处关键翻译缺口已用可重放的自有 App patch 修复，前后截图对比一致 ✓
- **POC-02 = PASS**
