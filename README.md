# MZ 个人月度对账系统

聚合微信、支付宝、银行账单，自动去重，计算当月真实总支出。

---

## 快速开始（CLI）

**安装**

```powershell
cd Personal-bill-recording-APP
python -m venv .venv
.venv\Scripts\Activate.ps1        # PowerShell 激活
pip install -e .
```

> **VSCode 用户（推荐）：** 按 `Ctrl+Shift+P` → 输入 `Python: Select Interpreter` → 选 `.venv\Scripts\python.exe`。设置一次后，VSCode 每次打开终端会自动激活虚拟环境，无需手动输命令。
>
> **手动激活：**
> - VSCode / PowerShell 终端：`.venv\Scripts\Activate.ps1`
> - CMD 终端：`.venv\Scripts\activate.bat`
> - Git Bash 终端：`source .venv/Scripts/activate`

**初始化（首次使用执行一次）**

```
mz init
```

按提示输入姓名，选择要跟踪的重点类目。

**查看支持的导入格式**

```
mz formats
```

---

## 日常使用流程

### 1. 导入账单

```
mz import <文件路径>
mz import <文件路径> --account 8223      # 手动指定银行卡号后四位
mz import <文件路径> --password <密码>   # 加密 PDF（工行默认：身份证后六位）
```

如果文件已导入过，加 `--account` 只会更新卡号标签，不重复入库。

支持的格式：

| 来源 | 格式 | 获取方式 |
|---|---|---|
| 微信支付 | `.xlsx` | 微信 → 我 → 服务 → 钱包 → 账单 → 常见问题 → 下载账单 |
| 支付宝 | `.csv` | 支付宝 → 我的 → 账单 → 下载账单 |
| 平安银行 | `.pdf` | 网银/手机银行导出流水 |
| 工商银行 | `.pdf` | 网银导出，加密密码为身份证后 6 位 |

### 2. 去重

所有账单导入后执行一次：

```
mz dedupe --month 2026-04
```

### 3. 查看报告

```
mz report --month 2026-04
```

报告中若有"⚠️ 待补账单"提示，说明某银行卡在已导入账单中出现但流水未导入，按提示补上后重新去重。

---

## 导入文件管理

```
mz list files
```

列出所有已导入账单文件，显示 ID、别名、来源、账单周期、条数和文件名。
别名格式：`来源_卡号后四位`（纯英文+数字），如 `pingan_8223`、`icbc_6930`、`wechat`、`alipay`。
银行 PDF 会自动尝试从首页文本提取卡号后四位；识别失败时别名为 `pingan_1`、`pingan_2`。

---

## 查看原始账单记录

```
mz list raw --month 2026-04                        # 查看所有来源的原始记录
mz list raw --source wechat --month 2026-04        # 按来源过滤
mz list raw --source bank_pingan --month 2026-04   # 只看平安银行记录
mz list raw --file pingan_8223 --month 2026-04     # 按别名过滤（见 mz list files）
mz list raw --file 3 --month 2026-04               # 按文件 ID 过滤
mz list raw --file pingan_8223 --month 2026-04 --transfers  # 同时显示内部转账记录
```

`--file` 优先于 `--source`。默认不显示已标记为内部转账的记录，加 `--transfers` 显示全部。

```
mz list shadows --month 2026-04
```

查看银行流水中含"财付通"/"支付宝"标记、但未能与 App 账单配对的记录（排查去重遗漏）。

---

## 调整入账状态

默认所有支出计入总支出，所有收入不计入。

```
mz list expense --month 2026-04   # 查看支出明细，找到交易 ID
mz list income  --month 2026-04   # 查看收入明细
mz list group   --month 2026-04   # 查看群收款

mz exclude <ID>                   # 排除某笔（不计入总支出）
mz include <ID>                   # 强制计入
mz offset <ID>                    # 让一笔收入抵充总支出（如收回的群分摊）
mz reset-inclusion <ID>           # 恢复自动模式
```

---

## 重点类目跟踪

```
mz category list                               # 查看所有类目及进度
mz category budget 旅游 --monthly 3000         # 设月预算（元）
mz category budget 旅游 --yearly 10000         # 设年预算（元）

mz entry add 旅游 1200 "机票" --date 2026-04-15           # 手动记录一笔
mz entry add 旅游 1200 "机票" --date 2026-04-15 --link <交易ID>  # 关联已有交易
```

---

## 重置与删除

```
mz db reset                    # 清空全部数据（二次确认，不可撤销）
mz db reset --force            # 跳过确认直接清空

mz delete-file pingan_8223     # 删除指定账单文件及其全部原始/规范交易记录
mz delete-file 3               # 按 ID 删除（ID 来自 mz list files）
```

删除单个文件后，重新导入正确文件并运行 `mz dedupe --month <月份>` 即可重新计算。

---

## 其他命令

```
mz coverage                  # 查看待补账单建议（哪些银行卡账单未导入）
mz explain <交易ID>           # 查看某笔交易的去重详情
mz db stats                  # 数据库记录数统计
mz formats                   # 支持的账单格式及导出方式说明
```

---

## 移动端 App（iOS / Android）

```bash
cd app
npm install
npx expo start    # 扫码用 Expo Go 打开
```

支持微信 XLSX 和支付宝 CSV 导入，暂不支持 PDF。

---

## 常用命令速查

| 命令 | 关键选项 | 用途 |
|---|---|---|
| `mz import <文件>` | `--account XXXX` `--password <密码>` | 导入账单 |
| `mz formats` | — | 查看支持的格式及导出说明 |
| `mz dedupe` | `--month YYYY-MM` | 跨平台去重（必须指定月份） |
| `mz report` | `--month YYYY-MM` `--format table/json/md` | 月度报告 |
| `mz list files` | — | 已导入账单文件列表（含 ID 和别名） |
| `mz list expense` | `--month YYYY-MM` | 支出明细 |
| `mz list income` | `--month YYYY-MM` | 收入明细 |
| `mz list group` | `--month YYYY-MM` | 群收款明细 |
| `mz list raw` | `--source X` `--file <ID或别名>` `--month YYYY-MM` `--transfers` | 原始账单记录 |
| `mz list shadows` | `--month YYYY-MM` | 未匹配的银行影子记录 |
| `mz exclude <ID>` | — | 排除某笔交易 |
| `mz include <ID>` | — | 强制计入某笔 |
| `mz offset <ID>` | — | 收入抵充支出 |
| `mz reset-inclusion <ID>` | — | 恢复自动模式 |
| `mz coverage` | — | 待补账单建议 |
| `mz category list` | — | 类目进度 |
| `mz category budget <名称>` | `--monthly N` `--yearly N` | 设预算 |
| `mz entry add <类目> <金额> <说明>` | `--date YYYY-MM-DD` `--link <ID>` | 手动记录类目支出 |
| `mz explain <ID>` | — | 查看去重详情 |
| `mz db stats` | — | 数据库统计 |
| `mz db reset` | `--force` | 清空数据库（危险，不可撤销） |
| `mz delete-file <ID或别名>` | `--force` | 删除指定账单文件及其全部记录 |
