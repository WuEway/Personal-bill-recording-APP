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

列出所有已注册的账单格式（来源名称、支持的文件扩展名、加密提示等），导入前可先确认格式是否受支持。

---

## 日常使用流程

### 1. 导入账单

```
mz import <文件路径>
```

支持的格式：

| 来源 | 格式 | 获取方式 |
|---|---|---|
| 微信支付 | `.xlsx` | 微信 → 我 → 服务 → 钱包 → 账单 → 常见问题 → 下载账单 |
| 支付宝 | `.csv` | 支付宝 → 我的 → 账单 → 下载账单 |
| 平安银行 | `.pdf` | 网银/手机银行导出流水 |
| 工商银行 | `.pdf` | 网银导出，加密密码为**身份证后 6 位** |

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

列出所有已导入账单文件。别名格式为 `来源_卡号后四位`（纯英文+数字），如 `pingan_8223`、`icbc_6930`、`wechat`、`alipay`。银行账单会自动尝试从 PDF 提取卡号后四位；如未识别到，别名为 `pingan_1`、`pingan_2` 等。

```
mz import <文件> --account 8223
```

导入时手动指定卡号后四位。如果该文件已导入过，只更新卡号标签，不重复入库。适用于 PDF 未能自动识别卡号的情况。

```
mz list raw --file <ID 或别名>
```

按文件查看原始记录，接受数字 ID（`--file 3`）或别名（`--file pingan_8223`）。`--file` 优先于 `--source`。

---

## 调整入账状态

默认所有支出计入总支出，所有收入不计入。

```
mz list expense --month 2026-04   # 查看支出，找到交易 ID

mz exclude <ID>                   # 排除（不计入支出）
mz offset <ID>                    # 让一笔收入抵充总支出（如收回的群分摊）
mz reset-inclusion <ID>           # 恢复自动模式
```

---

## 重点类目跟踪

```
mz category budget 旅游 --monthly 3000      # 设月预算

mz entry add 旅游 1200 "机票" --date 2026-04-15           # 手动记录
mz entry add 旅游 1200 "机票" --date 2026-04-15 --link <ID>  # 关联已有交易

mz category list                            # 查看所有类目进度
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

| 命令 | 用途 |
|---|---|
| `mz import <文件> [--account XXXX]` | 导入账单；`--account` 指定卡号后四位 |
| `mz formats` | 查看支持的导入格式 |
| `mz dedupe --month YYYY-MM` | 跨平台去重 |
| `mz report --month YYYY-MM` | 月度报告 |
| `mz list files` | 查看已导入账单文件列表 |
| `mz list expense --month YYYY-MM` | 支出明细 |
| `mz list income --month YYYY-MM` | 收入明细 |
| `mz list raw [--source X] [--file N]` | 原始账单记录（可按来源或文件编号过滤） |
| `mz list shadows` | 查看未匹配的银行影子记录 |
| `mz exclude <ID>` | 排除某笔 |
| `mz offset <ID>` | 收入抵充支出 |
| `mz coverage` | 待补账单建议 |
| `mz category list` | 类目进度 |
| `mz db stats` | 数据库统计 |