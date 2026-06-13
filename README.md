本仓库用于存储本学期现代数据库课程的族谱管理项目。
特殊的，本项目使用totemdb来搭建实现
具体环境已在wsl中配置完成，可以参考env.md进行配置

不要修改 resources 文件夹及里面的 defaultpic.jpg。


# 族谱管理系统（Totem 版）

本仓库用于存储本学期现代数据库课程的族谱管理项目。  
**当前环境：Totem 对象代理数据库，运行于 WSL（Ubuntu）。**

不要修改 `resources` 文件夹及里面的 `defaultpic.jpg`。

---

## 环境要求

- WSL（Ubuntu 18.04 LTS 64位，推荐）
- Totem 数据库已安装于 `/usr/local/totem`，版本 1.0
- Python 3.12（通过 conda 管理）
- `tsql` 和 `totem_dump` 可以直接在命令行中使用

> 注意：本项目使用 **Totem** 数据库，而非 PostgreSQL。  
> 命令行工具与 PostgreSQL 有所不同：  
> - 用 `tsql` 代替 `psql`  
> - 用 `totemctl` 启动/停止数据库服务  
> - 用 `totem_dump` 进行数据库备份，代替 `pg_dump`

### 1. 启动 Totem 数据库服务

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -l logfile start
```

验证连接是否成功：

```bash
/usr/local/totem/bin/tsql -d postgres
```

### 2. 创建数据库（首次运行）

```bash
/usr/local/totem/bin/createdb genealogy_db
```

### 3. 创建 conda 环境并安装依赖

```bash
conda create --name genealogy python=3.12.13 -y
conda activate genealogy
pip install -r requirements.txt
```

### 4. 初始化表结构

在 `tsql` 中执行初始化脚本：

```bash
/usr/local/totem/bin/tsql -d genealogy_db
```

```sql
\i init_db.sql
```

或直接从命令行执行：

```bash
/usr/local/totem/bin/tsql -d genealogy_db -f init_db.sql
```

### 5. 生成模拟数据

```bash
python generate_data.py
```

### 6. 导入数据

```bash
python load_db.py
```

> `load_db.py` 内部使用 Totem 的 `\COPY` 命令导入 `members_load.csv`，  
> 导入语句格式参考：
> ```sql
> \COPY members(member_id, clan_id, name, gender, father_id, mother_id, generation_num, bio)
> FROM 'members_load.csv'
> WITH (FORMAT CSV, NULL '');
> ```

### 7. 运行 Web 应用

```bash
uvicorn main:app --reload
```

---

## 数据库备份与导出

如需导出整个数据库，使用 Totem 提供的 `totem_dump` 工具：

```bash
/usr/local/totem/bin/totem_dump genealogy_db > genealogy_db_bck.sql
```

也可以通过 `export_db.py` 脚本自动导出：

```bash
python export_db.py
```

---

## 目录说明

```
.
├── main.py              # FastAPI 主程序
├── init_db.sql          # 建表脚本（适配 Totem SQL 语法）
├── generate_data.py     # 模拟数据生成脚本
├── load_db.py           # CSV 数据导入脚本
├── export_db.py         # 数据库导出脚本
├── requirements.txt     # Python 依赖
├── members_load.csv     # 生成的成员数据（由 generate_data.py 产生）
├── resources/
│   └── defaultpic.jpg   # 默认头像（勿修改）
└── README.md
```

---

## 注意事项

- Totem 的 SQL 语法与标准 PostgreSQL 基本兼容，但部分高级特性（如 `SERIAL`、`generate_series`、递归 CTE）需确认 Totem 版本是否支持，必要时用手动自增或 Python 脚本替代。
- Totem 中创建表使用 `CREATE CLASS` 语法（见用户手册），但本项目优先尝试标准 `CREATE TABLE`，如遇不兼容再切换为 `CREATE CLASS`。
- 若遇到连接失败，检查 Totem 服务是否已启动，以及 `totem_hba.conf` 中的认证配置是否允许本地连接。



