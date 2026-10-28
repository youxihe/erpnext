# BUILD-40 — 企微自建 H5 业务入口

日期：2026-10-29 ｜ 分支：`product/erpnext-wecom-ai-v1-20261029`
结论：**LOCAL_PASS（真实企微客户端 UAT 待 BUILD-30 外部配置就绪后补）**。
H5 部署在同一 ERPNext Site（同源免 CORS），四个核心入口全部走 BUILD-20 受控 API，实测真实写入。

## 1. 实现位置

- 页面：`cn_mfg_poc/www/wecom_h5.html + wecom_h5.py`，路由 **`/wecom_h5`**（移动端布局，无构建步骤）。
- 登录：访客显示免登面板；Mock 模式=选择成员模拟企微免登（本地联调）；真实模式=「企业微信免登」按钮走 `login_url` OAuth。免登成功 302 回工作台并种会话 Cookie。
- 数据：全部经 `/api/method/cn_mfg_poc.api.*`（会话身份 + 服务端角色校验 + CSRF Token），无共享管理员密钥，无第二套业务表。
- 注意：v16 的 www 页面 .py 上下文要求文件名为合法 Python 标识符，故用 `wecom_h5`（下划线）而非连字符（OBS-40-01）。

## 2. 四个核心入口（实测）

| 入口 | 操作人（企微绑定身份） | 实测结果 |
|---|---|---|
| 客户报备 | 王明（wangming-wx） | 表单提交 → **CRM-LEAD-2026-00003 苏州创力机械有限公司/吴经理/13700003333，报备人=wangming**（真实 Lead，查重逻辑内建） |
| 我的订单 | 王明 | 列表 4 张订单 + 交付/开票百分比 + 状态标签 |
| 我的任务 | 李工（ligong） | 只见本人任务（PO-JOB00001、PO-JOB00003），带「报工」按钮（pending>0 时），报工走 `update_job_progress`（幂等/防替他人） |
| 库存查询 | 张三（zhanggong，仓储） | 按仓查询：FASTENER 50 @原材料仓、RACK 2 @生产在制仓等，数值与 Bin 一致 |

端到端截图（移动端 400×780）：`docs/product/evidence/h5-*-1-login / 2-home / 3-* / 4-*.png`（13 张）。
驱动脚本：容器内 `/hostshare/h5flow.js`（puppeteer，免登→切 Tab→提交/报工→截图）。

## 3. 与 PC 的同源一致性

- H5 报备的客户 = PC「客户与销售→客户报备」同一 Lead 表，PC 立即可见；
- H5 报工 = PC「我的车间任务」报表同一 Job Card/Time Log；
- 身份链：企微 UserID → WeCom User Binding → ERP User（BUILD-30），H5 会话权限与 PC 登录完全一致（李工在 H5 看不到销售订单入口数据，API 层 403）。

## 4. 已知事项（登记 BACKLOG，不阻断）

- 任务卡片状态取 Job Card.status，个别已提交任务显示「已完成」但完成数 0.5/1（POC 旧数据 status 与数量不同步的历史口径），S2 待统一（OBS-40-02）。
- 真实企微客户端打开依赖 BUILD-30 的 4 项外部配置（CorpID/AgentID+Secret/可信 HTTPS 域名/通讯录授权）；配置后 H5 无需改动，仅关闭 Mock 模式。

## 5. 复测方式

```bash
# 容器内逐角色跑通（幂等；报备仅在客户名未建时创建，重复跑报「已存在」提示）
docker exec -e NODE_PATH=/workspace/tools/node_modules -w /hostshare poc-frappe \
  node /hostshare/h5flow.js ligong h5-li jobs
# 手机浏览器/企微内打开：http://erpnext-poc.localhost:18000/wecom_h5
```
