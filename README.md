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

> 每次打开新终端都需要先激活：`.venv\Scripts\Activate.ps1`

**初始化（首次使用执行一次）**

```
mz init
```

按提示输入姓名，选择要跟踪的重点类目。

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
| `mz import <文件>` | 导入账单 |
| `mz dedupe --month YYYY-MM` | 跨平台去重 |
| `mz report --month YYYY-MM` | 月度报告 |
| `mz list expense --month YYYY-MM` | 支出明细 |
| `mz list income --month YYYY-MM` | 收入明细 |
| `mz exclude <ID>` | 排除某笔 |
| `mz offset <ID>` | 收入抵充支出 |
| `mz coverage` | 待补账单建议 |
| `mz category list` | 类目进度 |
| `mz db stats` | 数据库统计 |