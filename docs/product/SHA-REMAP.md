# SHA 重映射说明（重要）

## 为什么会变

原仓库 `D:/ERP/erpnext` 是**浅克隆**（shallow clone，15 个浅边界、3332 个 commit）。
git 协议**禁止把浅仓库推送到远端**：

- 推空仓库时报 `remote: fatal: did not receive expected object <sha>`（远端校验父提交存在性）
- 换成接受 shallow 的路径时报 `shallow update not allowed`（`receive.shallowUpdate=false`）

GitHub 永远不会打开 `receive.shallowUpdate`。因此本仓库的三个代码分支是**重建**的：
保留全部 tree / message / author / committer，仅剥离指向浅边界之外的 parent，
使 15 个边界提交成为真正的 root commit。

**结果：commit 数量、提交信息、文件内容全部一致，只有 SHA 变了。**

- 重建后 commit 数：3332（含 15 个 root）
- 文件数（tip）：5821
- `git fsck` missing：0
- 新克隆 `is shallow: NO`

## 分支结构

| 分支 | SHA | 说明 |
|---|---|---|
| `product/erpnext-wecom-ai-v1-20261029` | `da311f66` | 主产品分支（含交接文档、DESK-HOME 修复） |
| `poc/erpnext-cn-manufacturing-20261026` | `87ea0143` | POC 分支 |
| `backup/local-before-sync-20261108` | `3486a0b3` | 同步前备份分支 |
| `main` | `883447f` | 完整交接文档 `HANDOVER-FULL.md`（含线上全部凭据） |
| `deliverable-snapshot` | `6b2f80a` | 自有代码/文档文件树快照（255 文件，无历史） |

## 关键提交 SHA 对照

| 旧 SHA（公开仓库 `youxihe/erpnext`） | 新 SHA（本私有仓库） | 内容 |
|---|---|---|
| `0cc61d37` | `da311f66` | product 分支 tip，交接文档补充快照分支说明 |
| `7a7f2d3c` | `f55400de` | 全量交接文档（公开脱敏版） |
| `d4e19107` | `96623842` | DESK-HOME 兼容修复（`/desk/home` → `/desk`） |
| `aff0b4f3` | `c569a17d` | PAGE-PERM-102：Desk User 补 Page.read |
| `a1e7ab17` | `fce8892b` | PORTAL-PERM-101：门户菜单按真实权限过滤 |

完整 3332 条映射：`_sha_mapping.json`（old -> new，JSON 对象）。

## 如何核对

```bash
git clone -b product/erpnext-wecom-ai-v1-20261029 git@github.com:youxihe/ai-erpnext.git
cd ai-erpnext
git log --oneline -5          # 提交信息与原来一致
git rev-list --count HEAD     # 3331
git fsck --connectivity-only  # 无 missing
```

需要对照证据文档里的旧 SHA 时，查 `_sha_mapping.json`；
或在公开仓库 `youxihe/erpnext` 里直接 `git show <旧SHA>`（那边历史完整、SHA 未变）。

## 完整上游历史

本仓库只含我们自己的 3332 个 commit（15 个 root 之前的上游历史未包含）。
需要完整 ERPNext 上游历史时，从 `youxihe/erpnext`（public fork）另行 clone。
