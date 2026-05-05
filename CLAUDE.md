# MZ 项目开发规范（Claude Code 持久指令）

## 文档同步规则（强制）

**每次代码变更必须同步更新文档，在同一个 commit 里完成：**

- 新增/修改/删除命令、参数、选项 → 更新 `README.md`
- 架构设计变更（数据模型、解析逻辑、去重策略等） → 更新 `MZ-Architecture.md`
- 文字力求清晰、简要。文档是代码的一部分，不能滞后于代码。

## 环境规范

- 所有 pip 安装必须在项目目录 `.venv` 虚拟环境中，不能污染系统 Python
- 激活方式：PowerShell `.venv\Scripts\Activate.ps1`，Bash `source .venv/Scripts/activate`

## 数据库安全

- **不能在未经用户明确要求的情况下删除 `~/.mz/data.db`**
- 测试和验证功能时在现有数据上追加，不要重置数据库
- Schema 变更使用 `ALTER TABLE ADD COLUMN`（无损 migration），在 `connection.py` 的 `_migrate()` 中管理

## README 命令文档要求

README 的"常用命令速查"表必须：
- 列出所有用户可用的命令及其关键选项
- 支持 `--month YYYY-MM` 的命令必须明确写出该参数
- 支持 `--file`、`--source`、`--account` 等过滤参数的命令必须注明

## 代码规范

- 新增银行导入器时，继承 `BaseImporter` 并实现 `extract_account_label()` 用于提取卡号后四位
- 银行文件别名格式：`<英文简称>_<卡号后四位>`，如 `pingan_8223`，不含中文
- 去重引擎任何修改须同步更新对应单元测试
