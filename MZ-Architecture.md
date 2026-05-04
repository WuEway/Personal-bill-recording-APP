# 个人月度对账系统 (MZ) — 系统设计与代码架构文档 v2

> **v2 关键变更（vs v1）**
> 1. 功能精简到两个：①月度总支出计算（去重）②重点类目限额跟踪
> 2. **删除**：自动分类（auto categorization）整套机制
> 3. **新增**：PDF / ZIP 文件解析 + 加密文件密码输入流程 + 文件格式声明
> 4. **重构**：账单展示改为「支出/收入」两个分支按时间排序
> 5. **新增**：每条交易的 include/exclude 标记；默认支出全选、收入全不选；用户可主动让某条收入抵充总支出
> 6. **新增**：群收款（含群发红包等）作为独立交易子类，默认不计入总支出，由用户决定
> 7. **强化**：基于已上传账单的关联推荐（A 账单引用 B 账户 → 提示上传 B 账单）
> 8. **测试数据**：用户已提供真实数据于 `G:\space_for_claude\记账本APP\交易记录`，含微信 XLSX、支付宝 CSV（GBK）、平安 PDF（带水印）、工商 PDF（加密）四种代表性格式

> 本文档面向 Claude Code 实施使用。读完即可直接编码，无需再做大的产品/架构决策。

---

## 目录

1. 项目目标与非目标
2. 核心产品概念
3. 技术栈与工程约束
4. 系统总体架构
5. 数据模型（SQLite Schema）
6. 模块详细设计
7. CLI 接口规范
8. 核心算法详解
9. 项目目录结构
10. 测试策略
11. 实施路线图
12. 待决策项 / 已知风险
13. 附录

---

## 1. 项目目标与非目标

### 1.1 核心功能（仅此两项）

**F1 — 月度总支出计算**

聚合用户从微信、支付宝、各家银行卡导出的账单文件，自动识别并去除跨平台重复，给出**当月真实总支出**这一单一可信数字。
- 收入与支出分支显示，按交易时间排序
- 默认所有"支出"条目计入总支出
- 默认所有"收入"条目**不**计入（不抵充）
- 群收款独立成一类，默认不计入；用户可逐条勾选某些收入抵充支出（如收回的群收款分摊）

**F2 — 重点类目限额跟踪**

用户主动声明若干"重点关注类目"（恋爱、旅游、培训、医疗、衣服等），每个类目可设置月限额或年限额，App 显示当前消费占限额的百分比。
- 用户主动录入或从已导入交易中标记
- 月限额：本月使用进度
- 年限额：本年累计进度
- 接近/超出限额时给出文字提示（不主动 push 通知）

### 1.2 非目标（明确不做）

- ❌ **不做自动分类**（去除饼图视图、规则匹配分类等所有自动归类逻辑）
- ❌ 不做实时通知监听 / SMS 解析 / 无障碍权限拦截
- ❌ 不做云同步、不做账号体系、不做多设备同步
- ❌ 不做移动端 UI（MVP 是 CLI + 后端引擎）
- ❌ 不做投资分析（理财买卖仅识别为内部转账并剔除）
- ❌ 不做家庭共享账本

### 1.3 支持的输入文件格式（必须明示给用户）

| 来源 | 格式 | 编码 / 特征 | 是否可能加密 |
|---|---|---|---|
| 微信支付账单 | `.csv` / `.xlsx` / `.zip` | UTF-8；ZIP 由微信下载默认带密码 | ZIP **常加密** |
| 支付宝账单 | `.csv` / `.zip` | **GBK** 编码；前 22 行为说明 | ZIP 偶有密码 |
| 银行流水 | `.pdf` / `.xlsx` / `.csv` | 各行不同 | PDF **常加密**（如工行）|

App 必须在导入界面明确列出"支持的格式"清单，并对每种格式提供导出操作指南链接。

---

## 2. 核心产品概念

### 2.1 三层资金视图

所有用户的资金流动归到下面三类的某一类：

| 层级 | 含义 | 默认是否计入"消费" |
|---|---|---|
| **A — 内部流转** | 自己名下账户互转（银行卡↔零钱、零钱↔零钱通、信用卡还款、余额宝赎回、提现） | ❌ 不计 |
| **B — 真实支出** | 钱真正流向第三方（商户、朋友、服务方） | ✅ 默认全计 |
| **C — 收入** | 外部资金进入（工资、转账收入、退款） | ❌ 默认不计；**用户可逐条勾选抵充** |

去重引擎的本质：**正确识别每条 raw 属于 A/B/C 中的哪一类，并对 B 做跨平台去重。**

### 2.2 影子记录

用户用微信支付一笔，绑定的银行卡同时扣款。两条记录指向同一笔真实消费：
- 微信账单里那条 → **主记录**（含商户名、订单号、时间精确）
- 银行账单里那条 → **影子记录**（仅"财付通"笼统标签）

去重 = 识别影子记录 → 链接到主记录 → 最终账单只保留主记录。

### 2.3 收入处理的"opt-in 抵充"原则

收入数据全部入库、全部展示，但默认**不参与总支出计算**。用户可对每条收入做出选择：

- **保持不抵充**（默认）：典型如工资、退款入零钱
- **勾选抵充**：典型如"我先垫付的群收款，王腾后来又转给我 ¥78"——用户主动把这 ¥78 当成"实质上没花"
- **永久剔除**（标记 ignore）：典型如理财利息、明显不属于个人消费的入账

总支出公式：
```
当月总支出 = ∑(direction=expense AND inclusion!=excluded) 
          - ∑(direction=income AND inclusion=offset)
```

### 2.4 群收款独立处理

微信"群收款"既可能是出（你给别人发的群收款里你的份额），也可能是入（别人发给你的份额）。
- 在 raw_transactions 标记 `is_group_payment=1`
- UI 上以独立小类展示（不混在"支出"或"收入"里）
- **默认全部不计入总支出**
- 用户可逐条选择是否计入（出向群收款）或抵充（入向群收款）

### 2.5 重点类目（仅 F2 使用）

- 用户在 onboarding 选定 3-7 个候选类目（默认池见 §6.6）
- 每个类目可设月预算、年预算（二者可同时存在或只设其一）
- 类目支出来源：用户手动录入 + 标记已有 raw 交易
- App 给出文字进度提醒，例：「本月恋爱支出 ¥1,200 / ¥1,500，已用 80%」

---

## 3. 技术栈与工程约束

### 3.1 强制选择

- **语言**：Python 3.11+
- **CLI 框架**：`click` 8.x
- **存储**：SQLite（标准库 `sqlite3`，不引入 ORM；schema 用 SQL 文件管理）
- **结构化数据**：`pandas` + `openpyxl`（处理 .xlsx）
- **PDF 解析**：`pdfplumber`（首选，含 layout）+ `pypdf` 5.x（密码、加解密）
- **ZIP 解压**：标准库 `zipfile`（已支持密码：`extractall(pwd=...)`），不需额外依赖
- **GBK CSV**：标准 `csv` + 自动编码检测（先尝试 utf-8，失败回退 gbk / gb18030）
- **数据模型**：`pydantic` v2
- **终端 UI**：`rich`（表格 / 进度条 / 颜色）
- **测试**：`pytest`
- **包管理**：`uv` 或 `poetry`
- **代码风格**：`ruff` + `mypy --strict`

### 3.2 设计原则

1. **本地优先**：所有数据存 `~/.mz/data.db`，不发送原始数据到外部服务
2. **可重入**：同一文件二次导入不产生重复（按文件 SHA256 去重）
3. **可解释**：每条去重决策留 `match_reason`，CLI 可 `mz explain <id>`
4. **可逆**：用户可撤销 include/exclude / 类目分配；可全量重跑
5. **离线运行**：MVP 不依赖任何在线服务

### 3.3 安全与隐私

- DB 文件权限 0600；默认在用户 home 目录下
- 日志不打印金额、对方姓名、商户名（仅打印交易 ID 和事件类型）
- 任何加密文件的密码**只用于本次会话解密**，不持久化到数据库
- 临时解密产物（如解压后的明文文件）放在 `~/.mz/tmp/` 并在导入完成后立即删除

---

## 4. 系统总体架构

```
┌────────────────────────────────────────────────────────────────┐
│                       CLI Layer (click)                         │
│  init / import / dedupe / report / coverage / category /        │
│  entry / inclusion / explain / db                               │
└─────────────────────────────┬──────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│                       Service Layer                             │
│  ┌────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐      │
│  │ File   │→ │ Importer │→ │  Dedupe  │→ │  Inclusion  │      │
│  │Unpack  │  │  Service │  │  Engine  │  │   Manager   │      │
│  └────────┘  └──────────┘  └──────────┘  └─────────────┘      │
│       ↑           ↓             ↓               ↓               │
│  password    Transfer       Coverage         Manual            │
│  prompt      Detector       Detector         Category          │
│                                              Tracker            │
│                              ↓                                  │
│                          Reporter                               │
└─────────────────────────────┬──────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────┐
│              Domain / Data Layer                                │
│  models (Pydantic)  •  repositories  •  SQLite                 │
└────────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────┴──────────────────────────────────┐
│              Adapters (per-source parsers)                      │
│   wechat_xlsx  alipay_csv  pingan_pdf  icbc_pdf  ccb_pdf  ...  │
└────────────────────────────────────────────────────────────────┘
```

**数据流**：
```
原始文件 (.csv/.xlsx/.pdf/.zip) 
    ↓ FileUnpack（解 ZIP，必要时索取密码）
    ↓ 文件类型 + 来源识别（自动 detect 或用户指定 hint）
    ↓ Adapter 解析 → RawTransactionDraft
    ↓ 写入 raw_transactions
    ↓ TransferDetector 标记 is_internal_transfer + is_group_payment
    ↓ DedupeEngine 跨平台匹配
    ↓ 写入 transactions（保留主记录、链接影子）
    ↓ InclusionManager 设置 default inclusion
    ↓ Reporter 聚合
两分支报表（支出 / 收入）+ 重点类目进度
```

---

## 5. 数据模型（SQLite Schema）

完整 SQL 在 `mz/db/schema.sql`。

### 5.1 `accounts` — 账户

```sql
CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    type            TEXT NOT NULL,           -- 'bank_debit' | 'bank_credit'
                                             -- 'wechat_balance' | 'alipay_balance'
                                             -- 'huabei' | 'meituan_yuefu'
                                             -- 'yuebao' | 'lingqiantong' | 'unknown'
    name            TEXT NOT NULL,           -- 用户可见："平安储蓄卡(8223)"
    institution     TEXT,                    -- "平安银行" / "微信支付" / "工商银行"
    last_4          TEXT,                    -- 卡尾号（仅银行卡）
    is_credit       INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(type, last_4, institution)
);
```

### 5.2 `raw_transactions` — 原始账单条目

```sql
CREATE TABLE raw_transactions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source                  TEXT NOT NULL,       -- 'wechat' | 'alipay' | 'bank_pingan' | 'bank_icbc' | ...
    source_file_id          INTEGER NOT NULL,    -- FK to imported_files
    txn_time                TIMESTAMP NOT NULL,  -- 银行无时间则用日期 00:00:00
    amount_cents            INTEGER NOT NULL,    -- 用整数（分）存避免精度问题；正/负=入/出
    currency                TEXT NOT NULL DEFAULT 'CNY',
    counterparty            TEXT,                -- 商户名 / 转账对方
    description             TEXT,                -- 商品 / 备注
    payment_account_id      INTEGER,             -- FK to accounts
    txn_type_raw            TEXT,                -- "商户消费"/"转账"/"群收款"/...
    direction               TEXT NOT NULL,       -- 'expense' | 'income' | 'transfer'

    external_txn_id         TEXT,                -- 微信交易单号 / 支付宝订单号
    external_merchant_id    TEXT,                -- 商户单号
    raw_json                TEXT NOT NULL,       -- 完整原始行（调试 + 重处理用）
    imported_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 派生字段（导入后由 Detector 填）
    is_internal_transfer    INTEGER NOT NULL DEFAULT 0,
    transfer_reason         TEXT,                -- 'cc_repayment' / 'yuebao_in' / ...
    is_group_payment        INTEGER NOT NULL DEFAULT 0,  -- 群收款标记
    is_refund               INTEGER NOT NULL DEFAULT 0,  -- 退款标记

    UNIQUE(source, external_txn_id),
    FOREIGN KEY (source_file_id) REFERENCES imported_files(id),
    FOREIGN KEY (payment_account_id) REFERENCES accounts(id)
);

CREATE INDEX idx_raw_time      ON raw_transactions(txn_time);
CREATE INDEX idx_raw_source    ON raw_transactions(source);
CREATE INDEX idx_raw_account   ON raw_transactions(payment_account_id);
CREATE INDEX idx_raw_amount    ON raw_transactions(amount_cents);
```

**关键约定**：金额一律用 `amount_cents` 整数（人民币分）。展示时除以 100。

### 5.3 `transactions` — 去重后的规范交易

```sql
CREATE TABLE transactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_raw_id      INTEGER NOT NULL,        -- 主记录
    txn_time            TIMESTAMP NOT NULL,
    amount_cents        INTEGER NOT NULL,
    counterparty        TEXT,
    description         TEXT,
    payment_account_id  INTEGER,
    direction           TEXT NOT NULL,           -- 'expense' | 'income'
                                                  -- transfer 类型不进此表

    is_group_payment    INTEGER NOT NULL DEFAULT 0,

    -- 用户可控字段（核心）
    inclusion           TEXT NOT NULL DEFAULT 'auto',
                                                  -- 'auto'      默认状态（按 direction 决定是否计入）
                                                  -- 'included'  显式计入
                                                  -- 'excluded'  显式剔除（不计入，灰色显示）
                                                  -- 'offset'    收入用于抵充支出（仅 income 行可设）
    inclusion_set_at    TIMESTAMP,
    inclusion_note      TEXT,                     -- 用户填写的原因（可选）

    -- 重点类目（F2）
    manual_category_id  INTEGER,
    manual_entry_id     INTEGER,                  -- 若由 manual_entry 触发的归类

    notes               TEXT,
    FOREIGN KEY (primary_raw_id) REFERENCES raw_transactions(id),
    FOREIGN KEY (payment_account_id) REFERENCES accounts(id),
    FOREIGN KEY (manual_category_id) REFERENCES manual_categories(id),
    FOREIGN KEY (manual_entry_id) REFERENCES manual_entries(id)
);

CREATE INDEX idx_txn_time      ON transactions(txn_time);
CREATE INDEX idx_txn_direction ON transactions(direction);
CREATE INDEX idx_txn_inclusion ON transactions(inclusion);
```

**计入规则（视图层应用）**：

| direction | inclusion=auto | inclusion=included | inclusion=excluded | inclusion=offset |
|---|---|---|---|---|
| expense | 计入支出（+） | 计入支出（+） | 不计 | n/a |
| expense + group_payment | **不计**（默认） | 计入支出 | 不计 | n/a |
| income | 不计（默认） | n/a | 不计 | 抵扣支出（−） |

### 5.4 `dedup_links` — 去重链接

```sql
CREATE TABLE dedup_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_txn_id    INTEGER NOT NULL,
    raw_txn_id          INTEGER NOT NULL,
    match_confidence    REAL NOT NULL,           -- 0.0–1.0
    match_reason        TEXT NOT NULL,           -- 可读字符串
    match_method        TEXT NOT NULL,           -- 'exact' | 'fuzzy' | 'manual'
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (canonical_txn_id) REFERENCES transactions(id),
    FOREIGN KEY (raw_txn_id) REFERENCES raw_transactions(id),
    UNIQUE(raw_txn_id)
);
```

### 5.5 `manual_categories` — 重点类目

```sql
CREATE TABLE manual_categories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,
    icon                TEXT,                    -- emoji
    monthly_budget_cents  INTEGER,               -- NULL=未设
    yearly_budget_cents   INTEGER,               -- NULL=未设
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 5.6 `manual_entries` — 手动录入条目

```sql
CREATE TABLE manual_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id     INTEGER NOT NULL,
    txn_time        TIMESTAMP NOT NULL,
    amount_cents    INTEGER NOT NULL,            -- 始终为正
    description     TEXT,
    -- 两种用法：
    --   1. linked_txn_id NULL → 完全离线录入（如现金消费）
    --   2. linked_txn_id 非 NULL → 把已存在的 transaction 标记到本类目
    linked_txn_id   INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES manual_categories(id),
    FOREIGN KEY (linked_txn_id) REFERENCES transactions(id)
);
```

**注意**：当 `linked_txn_id` 不为空时，对应的 `transactions.manual_category_id` 也要同步写入，方便查询。

### 5.7 `imported_files` — 导入历史

```sql
CREATE TABLE imported_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    file_hash       TEXT NOT NULL UNIQUE,        -- SHA256
    file_format     TEXT NOT NULL,               -- 'csv' | 'xlsx' | 'pdf' | 'zip'
    is_encrypted    INTEGER NOT NULL DEFAULT 0,  -- 是否曾经加密
    period_start    DATE,
    period_end      DATE,
    row_count       INTEGER NOT NULL,
    imported_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**注意**：密码绝不写入数据库；仅在内存中临时使用。

### 5.8 `app_config`

```sql
CREATE TABLE app_config (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
-- 必有键：
--   user_name           用户姓名（用于识别"转账给自己"）
--   schema_version      '2'
--   onboarded           '1' 表示已完成 init
```

---

## 6. 模块详细设计

### 6.1 File Unpack & Format Detection

**职责**：在 Importer 之前，处理「ZIP 解压、PDF 解密、编码检测」三件事。

**接口**（`mz/services/file_unpack.py`）：

```python
from pathlib import Path
from typing import Iterator
from dataclasses import dataclass

@dataclass
class UnpackedFile:
    path: Path                # 解压/解密后可直接读的文件
    original_name: str        # 用户原始上传名（用于显示）
    format: str               # 'csv' | 'xlsx' | 'pdf'
    is_temp: bool             # True 表示用完应删除
    was_encrypted: bool

class PasswordRequired(Exception):
    """提示上层去问用户密码。"""
    def __init__(self, file_path: Path, hint: str):
        self.file_path = file_path
        self.hint = hint   # 如 "工商银行 PDF 通常以身份证后 6 位为密码"

class FileUnpacker:
    SUPPORTED_FORMATS = {'.csv', '.xlsx', '.xls', '.pdf', '.zip'}

    def unpack(
        self,
        file_path: Path,
        password: str | None = None,
    ) -> list[UnpackedFile]:
        """
        - .zip → 解压；如有密码而 password=None，抛 PasswordRequired
        - .pdf → 检测加密；如加密而 password=None，抛 PasswordRequired
        - .xlsx / .csv → 直接返回原文件包装

        ZIP 内可能含多个文件（如微信 ZIP 里有 CSV + 一份 PDF 凭证）。
        都返回；后续 Importer 自己判断要不要处理。
        """
```

**密码提示文案**（`mz/services/password_hints.py`）：

```python
# 各银行 PDF 默认密码规则（用户参考）
PASSWORD_HINTS = {
    'bank_icbc':    '工商银行：身份证后 6 位（默认）',
    'bank_ccb':     '建设银行：身份证后 6 位（默认）',
    'bank_pingan':  '平安银行：通常无密码',
    'bank_boc':     '中国银行：身份证后 6 位（默认）',
    'wechat_zip':   '微信账单 ZIP：导出时邮件中给出的 6 位数字',
    'alipay_zip':   '支付宝账单 ZIP：导出时设置的密码（一般无）',
}

def detect_source_for_password_hint(file_path: Path) -> str:
    """根据文件名启发式判断 source 用于显示提示。"""
    name = file_path.name
    if '工商' in name or 'ICBC' in name.upper(): return 'bank_icbc'
    if '建设' in name or 'CCB' in name.upper():  return 'bank_ccb'
    if '平安' in name or 'PINGAN' in name.upper(): return 'bank_pingan'
    if '中国银行' in name:                       return 'bank_boc'
    if '微信' in name and name.endswith('.zip'): return 'wechat_zip'
    if '支付宝' in name and name.endswith('.zip'): return 'alipay_zip'
    return 'unknown'
```

---

### 6.2 Importer

**抽象接口**（`mz/importer/base.py`）：

```python
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Iterator
from mz.models import RawTransactionDraft

class BaseImporter(ABC):
    SOURCE_NAME: str          # 'wechat' / 'alipay' / 'bank_pingan' / 'bank_icbc' / 'bank_ccb'
    DISPLAY_NAME: str         # '微信支付账单' / '工商银行流水'
    SUPPORTED_FORMATS: list[str]   # 例如 ['xlsx', 'csv']

    @abstractmethod
    def detect(self, file_path: Path, file_format: str) -> bool:
        """根据扩展名 + 文件头判断本 Importer 是否能处理。"""

    @abstractmethod
    def parse(self, file_path: Path, file_format: str) -> Iterator[RawTransactionDraft]:
        """逐行 yield。"""

    @abstractmethod
    def detect_period(self, file_path: Path, file_format: str) -> tuple[date, date]:
        """从文件元信息中提取覆盖时段。"""
```

#### 6.2.1 WechatXlsxImporter（`mz/importer/wechat.py`）

**输入特征**（基于真实样本验证）：
- XLSX 单 sheet
- 行 0-15 为 metadata（标题、时间范围、笔数统计、注释）
- 行 16 为 `----------------------微信支付账单明细列表--------------------`
- 行 17 为表头：`交易时间, 交易类型, 交易对方, 商品, 收/支, 金额(元), 支付方式, 当前状态, 交易单号, 商户单号, 备注`
- 行 18+ 为数据
- `交易时间` 已是 `datetime` 类型（openpyxl 自动解析）
- `金额(元)` 字段是 number 类型（无 ¥、无千分位），单位元
- `收/支` 取值 `'收入' | '支出' | '/' (中性)`

**解析要点**：
```python
# 跳过头部 metadata 直到匹配到表头
HEADER_MARKER = '----------------------微信支付账单明细列表--------------------'

class WechatXlsxImporter(BaseImporter):
    SOURCE_NAME = 'wechat'
    DISPLAY_NAME = '微信支付账单'
    SUPPORTED_FORMATS = ['xlsx']

    EXPECTED_HEADER = ('交易时间', '交易类型', '交易对方', '商品', '收/支',
                       '金额(元)', '支付方式', '当前状态', '交易单号', '商户单号', '备注')

    def parse(self, file_path, file_format):
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        # 找到表头行
        for row in rows:
            if row[:11] == self.EXPECTED_HEADER:
                break
        # 之后的行是数据
        for row in rows:
            if not row[0]:  # 空行跳过
                continue
            yield self._parse_row(row)

    def _parse_row(self, row) -> RawTransactionDraft:
        (time, txn_type, party, item, sign, amount, payment, status,
         txn_id, merchant_id, note) = row[:11]

        # 收/支 → direction + amount 符号
        if sign == '支出':
            direction, amount_signed = 'expense', -abs(amount)
        elif sign == '收入':
            direction, amount_signed = 'income', +abs(amount)
        else:  # '/' 中性 → transfer 候选（充值/提现等），后续 TransferDetector 复审
            direction, amount_signed = 'transfer', amount  # 保留原符号或为 0

        # 群收款标记
        is_group_payment = (txn_type == '群收款')

        return RawTransactionDraft(
            source='wechat',
            txn_time=time,
            amount_cents=int(round(amount_signed * 100)),
            counterparty=party,
            description=item,
            payment_method_raw=payment,
            txn_type_raw=txn_type,
            direction=direction,
            external_txn_id=txn_id,
            external_merchant_id=merchant_id,
            is_group_payment=is_group_payment,
            raw_json=dict(zip(self.EXPECTED_HEADER, row[:11])),
        )
```

#### 6.2.2 AlipayCsvImporter（`mz/importer/alipay.py`）

**输入特征**（基于真实样本验证）：
- 文件**编码 = GBK**（必须！）
- 前 22 行说明（含"特别提示"等）
- 行 23 为分隔条 `------------------------支付宝支付科技有限公司  电子客户回单------------------------`
- 行 24 为表头：`交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注,`
- 末尾每行有空字段（多余逗号）
- 部分 `交易订单号` 含末尾 Tab，须 strip
- `收/付款方式` 可能含 `&` 表示混合支付（如 `工商银行储蓄卡(6930)&红包`）→ 需要拆分；为简化 MVP，**取主要方式（'&' 之前的部分）**，红包记录到 raw_json
- `收/支` 含 `'收入' | '支出' | '不计收支'`

```python
import csv

class AlipayCsvImporter(BaseImporter):
    SOURCE_NAME = 'alipay'
    DISPLAY_NAME = '支付宝交易明细'
    SUPPORTED_FORMATS = ['csv']

    HEADER = ('交易时间', '交易分类', '交易对方', '对方账号', '商品说明', '收/支',
              '金额', '收/付款方式', '交易状态', '交易订单号', '商家订单号', '备注')

    def parse(self, file_path, file_format):
        # 用 GBK 读
        with open(file_path, 'r', encoding='gbk', errors='replace') as f:
            content = f.read()
        lines = content.splitlines()
        # 找到表头行
        header_idx = None
        for i, line in enumerate(lines):
            if line.startswith('交易时间,'):
                header_idx = i
                break
        if header_idx is None:
            raise ValueError("Cannot locate Alipay header row")
        reader = csv.reader(lines[header_idx + 1:])
        for row in reader:
            if not row or not row[0].strip():
                continue
            yield self._parse_row(row)

    def _parse_row(self, row) -> RawTransactionDraft:
        # 注意：每行末尾有空字段，row 可能有 13 列
        time_str, category, party, party_acc, item, sign, amount, \
            payment, status, txn_id, merchant_id, note = row[:12]
        time = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S')

        # 收/支映射
        if sign == '支出':
            direction, amount_signed = 'expense', -abs(float(amount))
        elif sign == '收入':
            direction, amount_signed = 'income', +abs(float(amount))
        else:  # '不计收支'
            direction, amount_signed = 'transfer', float(amount)

        # 拆分混合支付方式
        primary_payment = payment.split('&')[0].strip() if payment else None

        return RawTransactionDraft(
            source='alipay',
            txn_time=time,
            amount_cents=int(round(amount_signed * 100)),
            counterparty=party,
            description=item,
            payment_method_raw=primary_payment,
            txn_type_raw=category,
            direction=direction,
            external_txn_id=txn_id.strip().rstrip('\t'),
            external_merchant_id=merchant_id.strip().rstrip('\t'),
            is_group_payment=False,  # 支付宝无明确群收款标识
            raw_json={'full_payment': payment, 'note': note, ...},
        )
```

#### 6.2.3 PinganPdfImporter（`mz/importer/bank/pingan.py`）★

**输入特征**（基于真实样本验证）：
- PDF 含 `PAB` 字样水印（`B/A/P` 三字符散布在每页）— 文本提取后会和正文交错
- 第 1 页有标题、户名、时段；后续页有数据表
- 数据列（按视觉顺序）：`序号, 交易日期, 交易金额, 余额, 交易地点, 摘要, 备注, 交易对手信息`
- 中文字段被双倍渲染（如 `吴吴逸逸威威`）— PDF 的中文 glyph 重复或字间距问题
- 金额含 `+` / `-` 前缀

**解析策略**：
1. **首选**：用 `pdfplumber.extract_tables()` 直接提取表格（带 layout，能避开水印）
2. **兜底**：`extract_text()` 后行级清洗 — 去除 `^[B|A|P]$` 这种单字符行
3. 中文倍字符问题：`re.sub(r'(.)\1+', r'\1', text)` 折叠连续相同字符（仅对中文字段；金额/日期不能这么处理）

```python
import pdfplumber
import re

class PinganPdfImporter(BaseImporter):
    SOURCE_NAME = 'bank_pingan'
    DISPLAY_NAME = '平安银行个人账户交易明细'
    SUPPORTED_FORMATS = ['pdf']

    WATERMARK_CHARS = set('BAP')

    def detect(self, file_path, file_format):
        if file_format != 'pdf':
            return False
        with pdfplumber.open(file_path) as pdf:
            text = (pdf.pages[0].extract_text() or '')[:1000]
        return '平安银行' in text and '交易明细' in text

    def parse(self, file_path, file_format):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # 优先用 extract_tables（pdfplumber 自动忽略浮空字符）
                tables = page.extract_tables()
                for table in tables:
                    yield from self._parse_table_rows(table)

    def _parse_table_rows(self, table):
        # 第一行是表头，跳过
        header_seen = False
        for row in table:
            cleaned = [self._clean_cell(c) for c in row]
            if not header_seen:
                if any('交易日期' in (c or '') for c in cleaned):
                    header_seen = True
                continue
            if not any(cleaned):  # 空行
                continue
            yield self._parse_data_row(cleaned)

    def _clean_cell(self, cell):
        if cell is None:
            return None
        # 去除水印字符（仅当整行全是 BAP 字符时跳过；细粒度处理在金额日期字段）
        cell = cell.strip()
        # 折叠连续重复字符（中文倍字问题）
        cell = re.sub(r'([一-鿿])\1+', r'\1', cell)
        return cell

    def _parse_data_row(self, cells) -> RawTransactionDraft:
        seq, date_str, amount_str, balance, place, remark, note, counterparty = cells[:8]
        amount = float(amount_str.replace(',', ''))   # 金额带 +/- 前缀，float 可处理

        # 收支方向
        direction = 'income' if amount > 0 else 'expense'

        # 影子标记
        is_shadow_wechat = (note or '').strip() == '财付通' or '财付通' in (counterparty or '')
        is_shadow_alipay = (note or '').strip() == '支付宝' or '支付宝' in (counterparty or '')

        return RawTransactionDraft(
            source='bank_pingan',
            txn_time=datetime.strptime(date_str.strip(), '%Y-%m-%d'),  # 银行只有日期
            amount_cents=int(round(amount * 100)),
            counterparty=counterparty,
            description=f'{remark} | {note}',
            payment_method_raw='__SHADOW_WECHAT__' if is_shadow_wechat
                              else '__SHADOW_ALIPAY__' if is_shadow_alipay
                              else None,
            txn_type_raw=remark,
            direction=direction,
            external_txn_id=None,  # 平安 PDF 无单号
            external_merchant_id=None,
            is_group_payment=False,
            raw_json={'all_cells': cells},
        )
```

**额外**：从第 1 页头部提取户主姓名 + 卡号 + 时段，写到 ImportedFile 元数据。

#### 6.2.4 IcbcPdfImporter（`mz/importer/bank/icbc.py`）

**关键**：必须解密。在 FileUnpacker 已经解密的前提下，本 importer 拿到明文 PDF。

**列结构**（典型）：`卡号, 交易日期/时间, 摘要, 收入金额, 支出金额, 余额, 对方户名, 对方账号, 备注`（实际需要拿到样本验证）

由于工商 PDF 当前未解密，本节实现细节标记为 **TODO**：
- 在用户提供密码并解密后，先用 `pdfplumber.extract_tables()` 探查列结构
- 然后按平安的方式实现
- 影子识别：寻找 `备注/摘要 包含 "支付宝" / "财付通" / "微信"` 的条目

#### 6.2.5 CcbPdfImporter / 通用 GenericBankImporter

- CCB 实现思路同上，等用户提供样本
- `GenericBankImporter` 兜底：当无专用 importer 时，弹 CLI 提示让用户用 `--mapping` 参数声明列名映射（key=expected_field, value=column_index）

#### 6.2.6 Importer 注册与分发

```python
# mz/importer/__init__.py
from mz.importer.wechat import WechatXlsxImporter
from mz.importer.alipay import AlipayCsvImporter
from mz.importer.bank.pingan import PinganPdfImporter
from mz.importer.bank.icbc import IcbcPdfImporter

IMPORTERS: list[BaseImporter] = [
    WechatXlsxImporter(),
    AlipayCsvImporter(),
    PinganPdfImporter(),
    IcbcPdfImporter(),
]

def list_supported_formats() -> dict[str, list[str]]:
    """供 UI 展示。"""
    return {imp.DISPLAY_NAME: imp.SUPPORTED_FORMATS for imp in IMPORTERS}

def find_importer(file_path: Path, file_format: str, hint: str | None = None) -> BaseImporter:
    if hint:
        for imp in IMPORTERS:
            if imp.SOURCE_NAME == hint:
                return imp
        raise ValueError(f"未知 source: {hint}")
    for imp in IMPORTERS:
        if file_format in imp.SUPPORTED_FORMATS and imp.detect(file_path, file_format):
            return imp
    raise ValueError(f"无法识别文件: {file_path.name}")
```

---

### 6.3 Account Resolver（账户解析）

**职责**：从 raw 的 `payment_method_raw` 字符串解析或新建 account_id。

```python
# mz/services/account_resolver.py
import re
from mz.repositories import AccountRepository

# 平安银行储蓄卡(8223)、建设银行信用卡(3906)、工商银行储蓄卡(6930) 等
BANK_PATTERN = re.compile(r'(.+?)(储蓄卡|信用卡)\((\d+)\)')

# 已知简称 → 标准机构名
INSTITUTION_NORMALIZE = {
    '工商': '工商银行', 'ICBC': '工商银行',
    '建设': '建设银行', 'CCB': '建设银行',
    '平安': '平安银行', 'PINGAN': '平安银行',
    '中国银行': '中国银行', 'BOC': '中国银行',
}

class AccountResolver:
    def __init__(self, repo: AccountRepository):
        self.repo = repo

    def resolve(self, payment_method_raw: str | None, source: str) -> int | None:
        if not payment_method_raw:
            return None

        # 微信特殊值
        if payment_method_raw in ('零钱', '/'):
            return self.repo.get_or_create(
                type='wechat_balance', name='微信零钱',
                institution='微信支付', last_4=None
            ).id

        # Shadow 占位（在影子记录上设置）
        if payment_method_raw == '__SHADOW_WECHAT__':
            return self.repo.get_or_create(
                type='wechat_balance', name='微信支付（影子）',
                institution='微信支付', last_4=None
            ).id
        if payment_method_raw == '__SHADOW_ALIPAY__':
            return self.repo.get_or_create(
                type='alipay_balance', name='支付宝（影子）',
                institution='支付宝', last_4=None
            ).id

        # 银行卡
        m = BANK_PATTERN.match(payment_method_raw)
        if m:
            institution_raw, kind, last_4 = m.groups()
            institution = self._normalize_institution(institution_raw)
            type_ = 'bank_credit' if kind == '信用卡' else 'bank_debit'
            return self.repo.get_or_create(
                type=type_, name=payment_method_raw,
                institution=institution, last_4=last_4,
                is_credit=(kind == '信用卡'),
            ).id

        # 支付宝特殊余额
        if '余额宝' in payment_method_raw:
            return self.repo.get_or_create(
                type='yuebao', name='余额宝', institution='支付宝'
            ).id
        if '花呗' in payment_method_raw:
            return self.repo.get_or_create(
                type='huabei', name='花呗', institution='支付宝'
            ).id
        if '余额' in payment_method_raw and '银行' not in payment_method_raw:
            return self.repo.get_or_create(
                type='alipay_balance', name='支付宝余额', institution='支付宝'
            ).id

        # 兜底
        return self.repo.get_or_create(
            type='unknown', name=payment_method_raw, institution='unknown'
        ).id

    def _normalize_institution(self, raw):
        for k, v in INSTITUTION_NORMALIZE.items():
            if k in raw:
                return v
        return raw.strip(' -')
```

---

### 6.4 Transfer Detector（内部转账识别）

```python
# mz/services/transfer_detector.py
@dataclass
class TransferRule:
    name: str
    matcher: callable
    reason: str

RULES: list[TransferRule] = [
    # 微信"中性交易"全部当作 transfer（已由 source 判定 direction='transfer'）
    # 但具体 reason 要进一步判断

    # 信用卡还款
    TransferRule(
        'cc_repayment',
        lambda t: (t.txn_type_raw and '信用卡还款' in t.txn_type_raw)
                 or (t.counterparty and '信用卡' in t.counterparty
                     and t.description and '还款' in t.description),
        'cc_repayment',
    ),
    # 美团月付主动还款
    TransferRule(
        'meituan_yuefu_repay',
        lambda t: t.counterparty == '美团'
                 and t.description and '美团月付' in t.description
                 and '还款' in t.description,
        'meituan_yuefu_repayment',
    ),
    # 花呗还款
    TransferRule(
        'huabei_repay',
        lambda t: t.counterparty and '花呗' in t.counterparty
                 and t.description and '还款' in t.description,
        'huabei_repayment',
    ),
    # 余额宝转入/赎回
    TransferRule(
        'yuebao_in',
        lambda t: t.counterparty == '余额宝' and t.amount_cents < 0,
        'yuebao_purchase',
    ),
    TransferRule(
        'yuebao_out',
        lambda t: '余额宝' in (t.description or '') and t.amount_cents > 0,
        'yuebao_redeem',
    ),
    # 零钱通同理
    TransferRule(
        'lqt_in',
        lambda t: '零钱通' in (t.counterparty or '') and t.amount_cents < 0,
        'lqt_purchase',
    ),
    TransferRule(
        'lqt_out',
        lambda t: '零钱通' in (t.description or '') and t.amount_cents > 0,
        'lqt_redeem',
    ),
    # 充值 / 提现
    TransferRule(
        'topup',
        lambda t: t.txn_type_raw and ('充值' in t.txn_type_raw or '储蓄卡入账' in t.txn_type_raw),
        'topup',
    ),
    TransferRule(
        'withdrawal',
        lambda t: t.txn_type_raw and '提现' in t.txn_type_raw,
        'withdrawal',
    ),
    # 银行内部：跨行转账给自己 / 网银互转 → 在银行 importer 加规则
]

class TransferDetector:
    def __init__(self, user_name: str | None):
        self.rules = list(RULES)
        if user_name:
            # 自己转给自己（按用户姓名）
            self.rules.append(TransferRule(
                'self_transfer',
                lambda t: t.counterparty == user_name,
                'self_transfer',
            ))

    def detect(self, txn) -> str | None:
        """返回 reason；None 表示不是内部转账。"""
        for rule in self.rules:
            if rule.matcher(txn):
                return rule.reason
        # 直接根据 source-level direction='transfer' 兜底
        if txn.direction == 'transfer':
            return 'unknown_transfer'
        return None
```

**运行时机**：每次 import 完后、dedupe 之前，对所有 `is_internal_transfer=NULL` 的 raw 跑一遍。

---

### 6.5 Dedup Engine ★

（与 v1 基本一致，关键点重申）

#### 6.5.1 影子识别

```python
def is_app_shadow_in_bank(raw) -> str | None:
    """如果是银行流水的影子，返回 'wechat' / 'alipay'。"""
    if not raw.source.startswith('bank_'):
        return None
    text = (raw.counterparty or '') + ' ' + (raw.description or '')
    if '财付通' in text:
        return 'wechat'
    if '支付宝' in text or '蚂蚁' in text:
        return 'alipay'
    return None
```

#### 6.5.2 匹配规则

```python
def can_match(primary, shadow) -> tuple[bool, float, str]:
    # 必要：金额相等
    if abs(primary.amount_cents) != abs(shadow.amount_cents):
        return False, 0.0, ''
    # 必要：方向都是 expense
    if primary.direction != 'expense' or shadow.direction != 'expense':
        return False, 0.0, ''
    # 必要：账户尾号 + 机构匹配
    p_acc, s_acc = primary.payment_account, shadow.payment_account
    if p_acc.last_4 != s_acc.last_4 or p_acc.institution != s_acc.institution:
        return False, 0.0, ''
    # 必要：日期窗口 ±2 天
    delta = abs((primary.txn_time.date() - shadow.txn_time.date()).days)
    if delta > 2:
        return False, 0.0, ''

    confidence = {0: 1.0, 1: 0.95, 2: 0.85}[delta]
    reason = f'amount={abs(primary.amount_cents)/100:.2f},last_4={p_acc.last_4},date_delta={delta}'
    return True, confidence, reason
```

#### 6.5.3 贪心匹配 + 引擎主流程

（同 v1 §6.4.4-6.4.5；篇幅原因不重复）

#### 6.5.4 关键差异（v2）

- **群收款**也可能有 shadow（用户用银行卡付的群收款），按相同规则匹配
- 若 `primary.is_group_payment=1`，匹配出的 canonical 也保持 `is_group_payment=1`

---

### 6.6 Inclusion Manager（NEW · 核心新模块）

**职责**：管理每条 transaction 的 `inclusion` 字段；提供查询、批量修改、抵充计算等操作。

```python
# mz/services/inclusion.py
from typing import Literal

InclusionState = Literal['auto', 'included', 'excluded', 'offset']

class InclusionManager:
    def __init__(self, repo):
        self.repo = repo

    # ---- 单条操作 ----
    def set(self, txn_id: int, state: InclusionState, note: str = ''):
        """设置某条 transaction 的 inclusion。"""
        txn = self.repo.get(txn_id)
        # 校验：offset 仅 income 行可设
        if state == 'offset' and txn.direction != 'income':
            raise ValueError("'offset' only applies to income transactions")
        self.repo.update_inclusion(txn_id, state, note)

    def reset(self, txn_id: int):
        """重置为 auto。"""
        self.set(txn_id, 'auto', '')

    # ---- 批量操作 ----
    def bulk_set(self, txn_ids: list[int], state: InclusionState):
        for tid in txn_ids:
            self.set(tid, state)

    # ---- 计算 ----
    def compute_total(self, period: tuple[date, date]) -> ComputedTotal:
        """计算月度总支出（应用所有 inclusion 规则）。"""
        txns = self.repo.list_in_period(period)
        expense_sum = 0
        income_offset_sum = 0
        excluded_count = 0
        for t in txns:
            counted_in = self._effective_counts_in_total(t)
            if counted_in == 'expense':
                expense_sum += abs(t.amount_cents)
            elif counted_in == 'offset':
                income_offset_sum += abs(t.amount_cents)
            elif counted_in == 'excluded':
                excluded_count += 1
        return ComputedTotal(
            total_expense_cents=expense_sum - income_offset_sum,
            raw_expense_cents=expense_sum,
            offset_income_cents=income_offset_sum,
            excluded_count=excluded_count,
        )

    @staticmethod
    def _effective_counts_in_total(t) -> str:
        """根据 direction + is_group_payment + inclusion 决定一条交易是否计入。"""
        if t.inclusion == 'excluded':
            return 'excluded'
        if t.inclusion == 'offset' and t.direction == 'income':
            return 'offset'
        if t.inclusion == 'included':
            return 'expense' if t.direction == 'expense' else 'excluded'
        # auto:
        if t.direction == 'expense' and not t.is_group_payment:
            return 'expense'
        return 'excluded'   # group_payment / income default
```

```python
@dataclass
class ComputedTotal:
    total_expense_cents: int      # 最终展示给用户的"当月总支出"
    raw_expense_cents: int        # 不算抵充前的支出和
    offset_income_cents: int      # 用户勾选抵充的收入和
    excluded_count: int
```

---

### 6.7 Manual Category Tracker

**职责**：F2 重点类目限额跟踪。

#### 6.7.1 默认候选池

```python
DEFAULT_CATEGORY_POOL = [
    ('恋爱',       '💑'),
    ('衣服',       '👕'),
    ('培训学习',   '📚'),
    ('旅游',       '✈️'),
    ('医疗',       '🏥'),
    ('数码',       '📱'),
    ('宠物',       '🐱'),
    ('健身美容',   '💪'),
    ('演唱会·追星', '🎤'),
    ('游戏氪金',   '🎮'),
    ('手办收藏',   '🎎'),
    ('人情往来',   '🎁'),
    ('朋友聚餐',   '🍻'),
]
```

#### 6.7.2 服务接口

```python
class ManualCategoryService:
    def add_category(self, name: str, icon: str | None = None,
                     monthly_budget: float | None = None,
                     yearly_budget: float | None = None) -> int: ...

    def list_categories(self) -> list[ManualCategory]: ...

    def add_entry(
        self, category_id: int, amount: float, description: str,
        txn_time: datetime, linked_txn_id: int | None = None,
    ) -> int:
        """录入条目。如果 linked_txn_id 不空，把对应的 transaction.manual_category_id 同步设上。"""

    def get_progress(self, category_id: int, ref_time: datetime = None) -> CategoryProgress:
        """返回限额使用进度。"""
```

```python
@dataclass
class CategoryProgress:
    category_id: int
    name: str
    icon: str
    # 月度
    month_spent_cents: int
    monthly_budget_cents: int | None
    monthly_pct: float | None         # spent/budget
    # 年度
    year_spent_cents: int
    yearly_budget_cents: int | None
    yearly_pct: float | None
    # 文字提醒
    alert_text: str                    # 如 "本月已用 80%（恋爱 ¥1,200/¥1,500）"
```

#### 6.7.3 进度文字模板

```python
def make_alert(p: CategoryProgress) -> str:
    parts = []
    if p.monthly_budget_cents:
        if p.monthly_pct >= 1.0:
            parts.append(f'⚠️ 本月{p.name}已超 {(p.monthly_pct - 1) * 100:.0f}%')
        elif p.monthly_pct >= 0.8:
            parts.append(f'⚠️ 本月{p.name}已用 {p.monthly_pct * 100:.0f}%（{fmt(p.month_spent_cents)}/{fmt(p.monthly_budget_cents)}）')
        else:
            parts.append(f'本月{p.name} {fmt(p.month_spent_cents)}/{fmt(p.monthly_budget_cents)}（{p.monthly_pct * 100:.0f}%）')
    if p.yearly_budget_cents:
        parts.append(f'年度 {fmt(p.year_spent_cents)}/{fmt(p.yearly_budget_cents)}（{p.yearly_pct * 100:.0f}%）')
    return ' · '.join(parts)
```

---

### 6.8 Coverage Detector（账户关联推荐）

**职责**：基于已导入数据，给出"还应上传哪些账单"的建议。

**算法**：

```python
class CoverageDetector:
    def detect(self, period: tuple[date, date]) -> list[MissingAccount]:
        # 1. 收集"被引用"的账户（从 raw 数据）
        referenced = set()
        for r in self.repo.list_raw(period):
            # 微信/支付宝中的支付方式如指向银行卡 → 该卡被引用
            acc = r.payment_account
            if acc and acc.type in ('bank_debit', 'bank_credit'):
                referenced.add((acc.institution, acc.last_4, acc.type))

        # 2. 收集已导入的账户（即已上传账单覆盖的）
        imported = set()
        for f in self.repo.list_imported_files(period):
            # 从 imported_files.source + 解析出的 account 关联
            for acc in self.repo.accounts_for_source(f.source, period):
                imported.add((acc.institution, acc.last_4, acc.type))

        # 3. 差集
        missing_keys = referenced - imported

        # 4. 整理证据
        result = []
        for inst, last_4, type_ in missing_keys:
            evidence = self._gather_evidence(inst, last_4, period)
            result.append(MissingAccount(
                institution=inst,
                last_4=last_4,
                type=type_,
                evidence=evidence,
                priority=self._priority(evidence),
            ))

        # 5. 反向：若 bank 上有大量 财付通/支付宝 影子但孤儿率高 → 提示导入对应 App 账单
        for app in ('wechat', 'alipay'):
            orphan_pct = self._orphan_shadow_pct(app, period)
            if orphan_pct > 0.3:
                result.append(MissingAccount(
                    institution=app, last_4=None, type=f'{app}_balance',
                    evidence=[f'银行流水中存在大量 {app} 影子但未匹配 App 账单'],
                    priority='high',
                ))
        return sorted(result, key=lambda x: -evidence_score(x))
```

```python
@dataclass
class MissingAccount:
    institution: str
    last_4: str | None
    type: str
    evidence: list[str]   # 例：["微信 4 月有 8 笔使用此卡"]
    priority: str         # 'high' | 'medium' | 'low'
```

---

### 6.9 Reporter（报表）

**两分支视图**：

```python
@dataclass
class MonthlyReport:
    period: tuple[date, date]
    # 总数
    total_expense_cents: int        # 已应用 inclusion 规则
    raw_expense_cents: int          # 不算抵充
    offset_income_cents: int        # 抵充总额

    # 两分支按时间排序
    expense_branch: list[ReportRow]
    income_branch: list[ReportRow]
    group_payment_branch: list[ReportRow]   # 独立成一类

    # 重点类目进度（F2）
    category_progresses: list[CategoryProgress]

    # 关联推荐
    missing_accounts: list[MissingAccount]

@dataclass
class ReportRow:
    txn_id: int
    txn_time: datetime
    amount_cents: int            # 始终为正展示
    counterparty: str
    description: str
    payment_account_name: str
    inclusion: str
    is_group_payment: bool
    in_total: bool                # 是否被计入总支出
```

**输出格式**：
- 终端表格：`mz report --month 2026-04`（用 rich）
- JSON：`--format json`
- Markdown：`--format md`（生成可分享的报告）

---

## 7. CLI 接口规范

### 7.1 命令汇总

```
mz init                                    # 引导式初始化（含选默认类目）
mz formats                                 # 列出支持的文件格式（用户参考）
mz import <file> [--source NAME] [--password PWD]
mz dedupe [--month YYYY-MM]
mz coverage [--month YYYY-MM]              # 缺账户提示

# 收入/支出查看与勾选
mz list expense [--month YYYY-MM]
mz list income  [--month YYYY-MM]
mz list group   [--month YYYY-MM]          # 群收款独立分支
mz include  <txn-ids...>                   # 标记包含
mz exclude  <txn-ids...>                   # 标记排除
mz offset   <txn-ids...>                   # 收入用于抵充支出
mz reset-inclusion <txn-ids...>            # 恢复默认

# 重点类目
mz category list
mz category add <name> [--icon e] [--monthly N] [--yearly N]
mz category remove <name>
mz category set-budget <name> [--monthly N] [--yearly N]

mz entry add <category> <amount> <description> [--date YYYY-MM-DD] [--link txn-id]
mz entry list [--month YYYY-MM] [--category NAME]
mz entry remove <id>

# 报表
mz report [--month YYYY-MM] [--format table|json|md]

# 调试
mz explain <txn-id>
mz raw list [--source NAME] [--month YYYY-MM]
mz db reset / export / import
```

### 7.2 几个关键交互范例

#### `mz formats`

```
$ mz formats
支持的文件格式：

来源              格式            说明
─────────────────────────────────────────────────────────
微信支付账单      .xlsx, .csv     从微信"我→服务→钱包→账单→常见问题→下载账单"导出
                                  ZIP 包内一般有 CSV，下载邮件中给出 6 位密码
支付宝交易明细    .csv            "账单→设置→开具交易流水证明"导出（GBK 编码）
平安银行          .pdf, .xlsx     "我的账户→交易明细→申请回单"
工商银行          .pdf            "我的账户→历史明细→申请明细 PDF"，密码通常是身份证后 6 位
建设银行          .pdf            （同工行）

所有 PDF 银行账单可能加密；导入时如有密码请通过 --password 参数提供，
或在交互式提示时输入。
```

#### `mz import` 含密码处理

```
$ mz import "工商银行历史明细.pdf"
检测到加密 PDF。
来源猜测：工商银行（密码通常为身份证后 6 位）
请输入密码: ******
✓ 解密成功
✓ 解析 47 行
✓ 已导入 47 条交易（period: 2026-04-01 到 2026-04-30）
✓ 检测到 3 笔内部转账（1×信用卡还款, 2×余额宝赎回）

提示：本次导入引用了下列账户但未上传对应账单：
  • 建设银行信用卡(3906) — 微信账单中出现 8 次，建议上传
运行 `mz coverage` 查看完整建议。
```

#### `mz list expense`

```
$ mz list expense --month 2026-04

2026-04 支出分支（按时间倒序）

ID    时间                金额      对方                 来源       计入  
──────────────────────────────────────────────────────────────────────────
1234  04-30 20:08:50    ¥103.08   x***8                Alipay     ✓
1235  04-30 19:44:11    ¥  6.00   怪兽充电              WeChat     ✓
1236  04-30 18:28:14    ¥ 14.50   高德打车              Alipay     ✓
1237  04-30 18:04:19    ¥  4.00   深圳通                Alipay     ✓
1238  04-30 12:30:00    ¥ 99.00   深圳大学城校园服务    WeChat     ✓
1239  04-29 13:22:56    ¥144.00   刘笑                  WeChat     ✓
1240  04-26 19:27:46    ¥238.34   群收款给王腾          WeChat     ☐ (group)
...

合计（已计入）: ¥12,345.67
共 84 条；其中 2 条 group_payment 未计入
```

#### `mz list income`

```
$ mz list income --month 2026-04

2026-04 收入分支（按时间倒序）

ID    时间                金额      对方             备注              抵充  
─────────────────────────────────────────────────────────────────────────────
1300  04-30 20:04:18    ¥600.00   燕窝             转账备注:微信转账  ☐
1301  04-29 +2666.67     ¥2666.67  哈工大深圳       助学金            ☐
1302  04-26 19:43:17    ¥147.25   王腾             群收款             ☐
1303  04-26 19:27:37    ¥ 78.34   王腾             群收款             ☐
1304  04-22 +1893.92     ¥1893.92  哈工大深圳       薪金              ☐
...

提示：用 `mz offset 1303` 把"王腾的群收款 ¥78.34"用于抵充本月支出。
```

#### `mz report`

```
$ mz report --month 2026-04

╔════════════════════════════════════════════════════════════╗
║   月度账单 — 2026-04                                       ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║   📊 当月总支出  ¥12,267.33                                ║
║       ├─ 原始支出  ¥12,345.67                              ║
║       ├─ 收入抵充  ¥    78.34  (1 项)                      ║
║       └─ 群收款已计入  ¥0.00（默认全部不计）               ║
║                                                            ║
║   📥 当月收入  ¥5,309.96  (默认不抵充)                     ║
║                                                            ║
║   📌 重点类目                                              ║
║      💑 恋爱        ¥1,200/¥1,500  本月 80%                ║
║      ✈️ 旅游        ¥  580/—       年度 12%                ║
║      📚 培训        ¥3,000/¥5,000  本月 60%                ║
║      🏥 医疗        ¥  155/¥  500  本月 31%                ║
║                                                            ║
║   ⚠️  待补账单                                             ║
║      • 建设银行信用卡(3906) — WeChat 中有 8 笔             ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

#### `mz explain`

```
$ mz explain 1238

Canonical Transaction #1238
  时间          2026-04-30 12:30:00
  金额          ¥99.00
  对方          深圳大学城校园服务
  说明          LWtb0H:177752...:卡片充值
  支付账户      平安银行储蓄卡(8223)
  方向          expense
  inclusion     auto → 计入支出
  是否群收款    否

源记录合并：
  • [self]  raw#789 (wechat)         主记录
       原"支付方式": 平安银行储蓄卡(8223)
  • [match] raw#1023 (bank_pingan)   影子, conf=1.00
       原 备注: 财付通

匹配理由：金额相同（¥99.00），账户尾号匹配（8223），日期同日。
银行记录为影子，从最终支出中剔除（保留微信记录因含商户名）。
```

---

## 8. 核心算法详解

### 8.1 文件解包流程

```python
def import_file(file_path: Path, password: str | None = None):
    # Step 1: 计算 hash 防重复
    h = sha256_of(file_path)
    if repo.imported_file_exists(h):
        print(f"该文件已导入过，跳过。")
        return

    # Step 2: 解包
    try:
        unpacked = unpacker.unpack(file_path, password=password)
    except PasswordRequired as e:
        # CLI 提示用户输入密码
        pwd = click.prompt(
            f"文件已加密。{e.hint}\n请输入密码",
            hide_input=True,
        )
        unpacked = unpacker.unpack(file_path, password=pwd)

    # Step 3: 对每个解包出来的子文件
    for u in unpacked:
        importer = find_importer(u.path, u.format, hint=user_hint)
        period = importer.detect_period(u.path, u.format)
        # 创建 imported_file 记录
        file_id = repo.create_imported_file(
            source=importer.SOURCE_NAME,
            file_path=str(file_path),
            file_hash=h,
            file_format=u.format,
            is_encrypted=u.was_encrypted,
            period_start=period[0],
            period_end=period[1],
        )
        # 解析每行
        count = 0
        for draft in importer.parse(u.path, u.format):
            account_id = account_resolver.resolve(draft.payment_method_raw, draft.source)
            repo.insert_raw(draft, source_file_id=file_id, payment_account_id=account_id)
            count += 1
        repo.update_file_row_count(file_id, count)

        # 清理临时文件
        if u.is_temp:
            u.path.unlink(missing_ok=True)
```

### 8.2 PDF 加密处理

```python
import pypdf

def is_pdf_encrypted(file_path: Path) -> bool:
    reader = pypdf.PdfReader(str(file_path))
    return reader.is_encrypted

def decrypt_pdf(in_path: Path, out_path: Path, password: str) -> bool:
    reader = pypdf.PdfReader(str(in_path))
    if not reader.is_encrypted:
        return True
    rc = reader.decrypt(password)
    if rc == 0:  # 密码错误
        return False
    writer = pypdf.PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    with open(out_path, 'wb') as f:
        writer.write(f)
    return True
```

### 8.3 ZIP 加密处理

```python
import zipfile

def unpack_zip(zip_path: Path, dest: Path, password: str | None) -> list[Path]:
    with zipfile.ZipFile(zip_path) as zf:
        # 检查是否需要密码
        try:
            zf.testzip()
            needs_pwd = False
        except RuntimeError:
            needs_pwd = True
        if needs_pwd and not password:
            raise PasswordRequired(zip_path, '微信账单 ZIP 通常密码为下载邮件中的 6 位数字')
        pwd_bytes = password.encode() if password else None
        out = []
        for name in zf.namelist():
            extracted = zf.extract(name, path=dest, pwd=pwd_bytes)
            out.append(Path(extracted))
        return out
```

### 8.4 平安 PDF 水印清理

实测发现平安 PDF 的水印是 `B`/`A`/`P` 三个字母散布在每页中。`pdfplumber.extract_text()` 会把它们和正文混在一起；但 `extract_tables()` 会基于布局 box 对齐，能避开水印。

```python
import pdfplumber

def parse_pingan(file_path):
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(table_settings={
                'vertical_strategy': 'lines',
                'horizontal_strategy': 'lines',
                'min_words_vertical': 1,
            })
            for table in tables:
                for row in table:
                    yield clean_row(row)
```

如表格结构识别失败，兜底用 `extract_text()` + 行级 regex 提取（至少能处理 80% 的行）。

### 8.5 中文重复字符清理

平安 PDF 文本提取会出现 `吴吴逸逸威威` 这种"每个字符重复 2 次"现象（因水印图层叠加）。**仅对纯中文片段**做折叠：

```python
import re

def collapse_chinese_repeats(text: str) -> str:
    # 仅折叠中文连续重复，避开数字/英文字母（因为它们可能本来就重复）
    return re.sub(r'([一-鿿])\1+', r'\1', text)
```

### 8.6 退款冲销

```python
def find_and_link_refunds(period):
    """
    支付宝/微信中的退款会单独成行（金额为正，direction=income）。
    找到对应原交易并把退款链接到它，最终 canonical 的 amount 应反映净额。
    """
    refunds = repo.list_raw(
        period=period, direction='income',
        description_contains='退款',
    )
    for r in refunds:
        # 通过 external_merchant_id 找原交易
        original = repo.find_raw(
            source=r.source,
            external_merchant_id=r.external_merchant_id,
            direction='expense',
        )
        if original:
            r.is_refund = 1
            r.linked_to_raw_id = original.id
            repo.update(r)
```

退款应用到 transactions 时：原交易 amount 减去退款额；若全额退款则原交易标记 inclusion=excluded。

### 8.7 跨周期影子匹配

dedupe 跑某月时，候选影子的范围扩展到该月起始 −3 天 至该月末 +3 天。匹配后影子可能落在外月，但 transactions 仍按主记录的时间归属。

---

## 9. 项目目录结构

```
mz/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md                  # 本文档
├── ruff.toml
├── mypy.ini
├── .gitignore
│
├── mz/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py                  # click app 入口
│   │   ├── commands/
│   │   │   ├── init.py
│   │   │   ├── formats.py
│   │   │   ├── import_.py
│   │   │   ├── dedupe.py
│   │   │   ├── list_.py             # list expense / income / group
│   │   │   ├── inclusion.py         # include / exclude / offset / reset
│   │   │   ├── category.py
│   │   │   ├── entry.py
│   │   │   ├── report.py
│   │   │   ├── coverage.py
│   │   │   ├── explain.py
│   │   │   └── db.py
│   │   └── ui.py                    # rich helpers
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── account.py
│   │   ├── transaction.py           # RawTransactionDraft / RawTransaction / Transaction
│   │   ├── category.py
│   │   └── report.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── schema.sql
│   │   └── migrations/
│   │       └── 001_initial.sql
│   │
│   ├── repositories/
│   │   ├── account_repo.py
│   │   ├── raw_txn_repo.py
│   │   ├── transaction_repo.py
│   │   ├── category_repo.py
│   │   └── imported_file_repo.py
│   │
│   ├── services/
│   │   ├── file_unpack.py           # ZIP/PDF 解包 + 密码
│   │   ├── password_hints.py
│   │   ├── account_resolver.py
│   │   ├── transfer_detector.py
│   │   ├── inclusion.py             # InclusionManager
│   │   ├── coverage.py
│   │   ├── reporter.py
│   │   └── dedupe/
│   │       ├── engine.py
│   │       └── matcher.py
│   │
│   ├── importer/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── wechat.py                # WechatXlsxImporter (+ csv 兼容)
│   │   ├── alipay.py                # AlipayCsvImporter
│   │   └── bank/
│   │       ├── base.py
│   │       ├── pingan.py            # PinganPdfImporter (+ xlsx)
│   │       ├── icbc.py              # IcbcPdfImporter (TODO 待样本)
│   │       ├── ccb.py               # CcbPdfImporter
│   │       └── generic.py
│   │
│   └── utils/
│       ├── hashing.py
│       ├── encoding.py              # detect_encoding, decode_with_fallback
│       ├── text.py                  # collapse_chinese_repeats, normalize_merchant
│       └── dates.py
│
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   ├── 微信支付账单流水文件(20260401-20260430)_20260504140155.xlsx
    │   ├── 支付宝交易明细(20260401-20260430).csv
    │   ├── 平安银行个人账户交易明细 JYLS260504097131.pdf
    │   ├── 工商银行历史明细（申请单号：26050419352753386489）.pdf  # 加密样本
    │   └── golden_2026_04/
    │       └── expected_report.json   # ground truth
    ├── unit/
    │   ├── test_importer_wechat.py
    │   ├── test_importer_alipay.py
    │   ├── test_importer_pingan.py
    │   ├── test_account_resolver.py
    │   ├── test_transfer_detector.py
    │   ├── test_dedupe_matcher.py
    │   ├── test_inclusion_manager.py
    │   └── test_reporter.py
    ├── integration/
    │   ├── test_full_pipeline.py
    │   └── test_coverage.py
    └── cli/
        ├── test_cli_import.py
        ├── test_cli_inclusion.py
        └── test_cli_report.py
```

---

## 10. 测试策略

### 10.1 真实数据 fixture（关键）

把用户提供的四份真实文件复制进 `tests/fixtures/`：
- `微信支付账单流水文件(20260401-20260430)_20260504140155.xlsx`
- `支付宝交易明细(20260401-20260430).csv`
- `平安银行个人账户交易明细 JYLS260504097131.pdf`
- `工商银行历史明细（申请单号：26050419352753386489）.pdf`（加密样本）

**配套**：在 `tests/fixtures/golden_2026_04/expected_report.json` 写入手工核算的 ground truth：
```json
{
  "period": ["2026-04-01", "2026-04-30"],
  "raw_transaction_counts": {
    "wechat": 89,
    "alipay": 97,
    "bank_pingan": 13
  },
  "internal_transfer_count": 13,
  "group_payment_count": 3,
  "expected_dedup_pairs": 10,
  "expected_total_expense_cents": "TBD-after-manual-check"
}
```

**强制**：CI 每次跑必须 100% 匹配 golden 数据；任何变动都要更新 expected。

### 10.2 单元测试覆盖

每个 Importer：
- 标准行 / 含中性交易 / 含群收款 / 跨日期边界
- 编码（GBK / UTF-8）/ 加密 / 表头偏移

每个 Service：
- TransferDetector：每条规则一个正例一个反例
- DedupeMatcher：金额/卡号/日期边界都覆盖
- InclusionManager：每种 (direction, is_group_payment, inclusion) 组合

### 10.3 集成测试 `test_full_pipeline.py`

```python
def test_full_pipeline_april_2026(tmp_path):
    # 1. init
    db = init_test_db(tmp_path)
    # 2. import all 4 files (icbc 用预解密版本)
    import_file(WECHAT_FIXTURE)
    import_file(ALIPAY_FIXTURE)
    import_file(PINGAN_FIXTURE)
    # 3. dedupe
    DedupeEngine().run(period=('2026-04-01', '2026-04-30'))
    # 4. compute total
    total = InclusionManager().compute_total(...)
    # 5. assert against golden
    expected = json.load(open('tests/fixtures/golden_2026_04/expected_report.json'))
    assert total.total_expense_cents == expected['expected_total_expense_cents']
```

### 10.4 性能基准

- 处理 500 行 PDF + 10000 条 raw 应在 10 秒内
- DedupeEngine 复杂度 O(N×M)；通过 (last_4, amount_cents) 索引把候选池砍到 < 50

---

## 11. 实施路线图

### Phase 1 — Skeleton（1-2 天）
- [ ] 项目初始化（pyproject、ruff、mypy、pytest）
- [ ] DB schema + connection + repositories
- [ ] CLI 骨架（click app）+ `mz init` + `mz formats`
- [ ] Pydantic 模型 + utils（hashing, encoding, text, dates）
- [ ] FileUnpacker（基础版本，支持 ZIP/PDF 加密 + 标准库 zipfile）

### Phase 2 — Importer（3-4 天）★ 重点
- [ ] WechatXlsxImporter + 单测（用真实 fixture）
- [ ] AlipayCsvImporter + GBK 编码处理 + 单测
- [ ] PinganPdfImporter + 水印清理 + 单测
- [ ] AccountResolver + 单测
- [ ] `mz import` CLI（含密码交互）
- [ ] 文件 hash 防重复导入
- [ ] **里程碑**：能跑通 4 月份所有 raw 数据导入

### Phase 3 — Transfer Detection + Dedupe（3 天）★ 重点
- [ ] TransferDetector + 全规则单测
- [ ] DedupeMatcher + 单测
- [ ] DedupeEngine 完整流程
- [ ] `mz dedupe` + `mz explain` CLI
- [ ] **里程碑**：写 golden_2026_04，跑通真实样本对账，总额数字与手算一致

### Phase 4 — Inclusion + Lists（2 天）
- [ ] InclusionManager 服务
- [ ] `mz list expense/income/group`
- [ ] `mz include / exclude / offset / reset-inclusion`
- [ ] 群收款独立分支显示

### Phase 5 — Manual Categories（2 天）
- [ ] ManualCategoryService + CLI
- [ ] 限额计算（月/年）+ 进度文字
- [ ] `mz entry add/list/remove`
- [ ] 链接 transactions 时同步更新

### Phase 6 — Coverage + Report（2 天）
- [ ] CoverageDetector
- [ ] Reporter（两分支视图 + 类目进度）
- [ ] `mz report` 三种 format（table / json / md）
- [ ] `mz coverage`

### Phase 7 — IcbcPdfImporter & 抛光（2 天）
- [ ] 用真实工商样本（用户提供密码）开发 ICBC importer
- [ ] CcbPdfImporter（待用户提供样本）
- [ ] 错误处理、日志、用户友好提示
- [ ] 完善 README + 演示视频

**Phase 总计估计：14-17 个工作日**

---

## 12. 待决策项 / 已知风险

### 12.1 待决策

1. **产品正式名**：`mz` 是代号
2. **金额精度**：已决定用 `amount_cents` 整数
3. **限额单位**：年限额是否按自然年（1.1-12.31）？还是按 12 个月滚动？默认**自然年**
4. **群收款发起者的处理**：发起群收款的人会看到一笔出账。这条要不要默认 group_payment？建议**是**（保持一致），由用户决定包括它的分摊部分还是全部
5. **混合支付（如支付宝"工商卡 + 红包"）**：MVP 取主要部分；红包部分如何记账留作 v2

### 12.2 已知风险

1. **银行 PDF 格式百花齐放**：每家不一样、可能改版。MVP 先攻平安+工商，预留 generic 兜底
2. **跨月影子边界**：dedupe 跑全量数据更稳；按月只在 report 视图过滤
3. **支付宝退款金额 0 的医保支付行**：实测 fixture 中存在多条 ¥0.00 医保支付，要专门处理（视为 transfer）
4. **PDF 解析失败兜底**：当 `extract_tables()` 返回空，要 fallback 到 `extract_text()` + regex；务必给出清晰错误信息

### 12.3 不在本期范围

- 多用户、共享账本
- 银行 API 直连
- 移动端
- 通知监听 / SMS 解析
- 自动分类（已明确删除）
- 投资分析

---

## 13. 附录

### 附录 A：用户操作示例（端到端）

```
$ mz init
> Welcome! 您的姓名: 吴逸威
> 选择重点类目（3-7 个）：恋爱、培训、医疗、衣服
> ✓ 初始化完成

$ mz formats
[显示支持的文件格式]

$ mz import "记账本APP/交易记录/微信支付账单流水文件(20260401-20260430)_20260504140155.xlsx"
✓ 解析 89 行（5 收入, 84 支出, 0 中性, 含 2 群收款）

$ mz import "记账本APP/交易记录/支付宝交易明细(20260401-20260430).csv"
✓ 解析 97 行（0 收入, 84 支出, 13 不计收支）

$ mz import "记账本APP/交易记录/平安银行个人账户交易明细 JYLS260504097131.pdf"
✓ 解析 13 行（3 收入, 10 影子）

$ mz import "记账本APP/交易记录/工商银行历史明细（申请单号：26050419352753386489）.pdf"
检测到加密 PDF。
来源：工商银行（密码通常为身份证后 6 位）
请输入密码: ******
✓ 解密成功，解析 N 行

$ mz dedupe --month 2026-04
✓ 匹配 10/10 wechat-pingan 影子（100%）
✓ 匹配 X/Y alipay-icbc 影子
当月候选总支出: ¥XX,XXX.XX

$ mz list group --month 2026-04
ID    时间               金额      对方   说明
1240  04-26 19:27:46    ¥238.34   王腾   群收款
1241  04-26 19:43:17    ¥147.25   王腾   群收款（收入）
1242  04-26 19:27:37    ¥ 78.34   王腾   群收款（收入）

$ mz offset 1242
✓ 已将 ¥78.34 标记为抵充

$ mz entry add 培训 10000 "深圳财政学费" --date 2026-04-24 --link 1180
✓ 类目"培训"已添加 ¥10,000；进度 100% 月度限额

$ mz coverage
⚠️ 缺失：建设银行信用卡(3906) — 微信账单中出现 8 次

$ mz report --month 2026-04
[显示完整月报]
```

### 附录 B：开发上手 Checklist

按下列顺序最避免返工：

1. 写 §5 完整 schema.sql
2. Pydantic 模型定型（draft → raw → canonical）
3. 实现 FileUnpacker（先支持 ZIP+ 标准 PDF，密码留 raise PasswordRequired）
4. 实现 WechatXlsxImporter（用真实 fixture 跑通）→ 加进 tests/fixtures
5. 实现 AlipayCsvImporter（GBK 处理是核心）
6. 实现 PinganPdfImporter（水印 + 表格提取）
7. 实现 AccountResolver
8. 实现 TransferDetector
9. **关键节点**：写 test_full_pipeline.py 先跑出"raw 总额"，对账正确再继续
10. 实现 DedupeEngine（matcher → engine → review）
11. 跑通去重，金额 = 手算
12. 实现 InclusionManager + list/inclusion CLI
13. 实现 ManualCategoryService + entry CLI
14. 实现 CoverageDetector
15. 实现 Reporter
16. 处理 IcbcPdfImporter（需用户密码）

---

**文档结束。** 实施过程中如发现需要调整设计，请在 commit 中标注 `[ARCH-DECISION]` 并更新本文档对应章节。
