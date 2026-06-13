# 环境配置与运行指南

本文件用于说明团队成员在 Windows 本地 clone 项目后，如何在 WSL 中启动 Totem 数据库、创建项目数据库、初始化表结构、导入示例数据，并运行 Web 系统。

项目代码位于 `project/` 目录。本文默认 WSL 发行版为 `Ubuntu-18.04`，Totem 安装路径为 `/usr/local/totem`，项目数据库名为 `genealogy`。

---

## 1. 进入 WSL 环境

在 Windows PowerShell 或 CMD 中查看 WSL 发行版：

```powershell
wsl -l -v
```

如果存在 `Ubuntu-18.04`，进入该环境：

```powershell
wsl -d Ubuntu-18.04
```

进入后建议先确认项目目录可访问：

```bash
cd /mnt/e/totemdb/project
ls
```

如果项目 clone 到其他盘符或目录，请把 `/mnt/e/totemdb/project` 替换为实际路径。

---

## 2. 启动 Totem 数据库服务

Totem 不能以 root 身份运行，需要使用专用用户 `totem`。

```bash
su - totem
```

首次安装后，如果还没有初始化数据目录，执行：

```bash
mkdir -p /usr/local/totem/data
/usr/local/totem/bin/initdb -D /usr/local/totem/data
```

日常启动数据库：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -l /tmp/totem.log start
```

检查状态：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data status
```

如果 5432 端口被占用，可改用其他端口，例如本项目测试过的 `55432`：

```bash
/usr/local/totem/bin/totemctl -w -D /usr/local/totem/data -l /tmp/totem-55432.log -o '-p 55432' start
```

之后所有 `tsql`、导入脚本、Web 启动命令都需要同步使用该端口。

---

## 3. 创建项目数据库

项目默认数据库名为 `genealogy`。如果本地还没有该数据库，先创建：

```bash
/usr/local/totem/bin/createdb genealogy
```

如果使用了非默认端口，例如 `55432`：

```bash
/usr/local/totem/bin/createdb -p 55432 genealogy
```

验证连接：

```bash
/usr/local/totem/bin/tsql -d genealogy
```

或指定端口：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy
```

进入后可执行：

```sql
\dt
```

新建空库时应显示没有表。

---

## 4. 初始化表结构

切换到项目目录：

```bash
cd /mnt/e/totemdb/project
```

执行建表脚本：

```bash
/usr/local/totem/bin/tsql -d genealogy -f init_db.sql
```

如果使用端口 `55432`：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -f init_db.sql
```

初始化完成后检查表：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -c '\dt'
```

应看到以下 5 张表：

- `users`
- `genealogies`
- `collaborations`
- `members`
- `marriages`

注意：当前 Totem 版本不支持 `CREATE TABLE IF NOT EXISTS`，并且对部分内联外键语法兼容性较弱，所以 `init_db.sql` 使用了更保守的主键、CHECK、索引方案。若重复执行 `init_db.sql`，会因为表已存在而报错；只有空数据库首次初始化时执行它。

---

## 5. 生成并导入示例数据

生成成员 CSV：

```bash
python generate_data.py
```

导入示例成员数据：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -f import_members.sql
```

验证导入结果：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -c 'SELECT COUNT(member_id) AS total FROM members;'
```

如需用 Python 脚本重新导入成员数据，可设置端口后运行：

```bash
export TOTEM_DATABASE=genealogy
export TOTEM_PORT=55432
python load_db.py
```

`load_db.py` 默认只清空并重新导入 `members` 表中 `clan_id = 1` 的成员数据，不会重复建表。若确实要让脚本同时执行建表，可额外设置：

```bash
export TOTEM_INIT_SCHEMA=1
```

但只有空数据库才建议这样做。

---

## 6. 创建 Python 运行环境

项目 Web 部分使用 FastAPI 与 Uvicorn。推荐使用 conda 的 Python 3.12 环境：

```bash
conda create --name genealogy python=3.12.13 -y
conda activate genealogy
pip install -r requirements.txt
```

如果已经创建过环境，只需：

```bash
conda activate genealogy
pip install -r requirements.txt
```

WSL 自带的 `python3` 可能是 3.6，无法运行本项目中的现代 Python 类型语法，因此不要直接使用系统默认 Python 启动 Web。

---

## 7. 启动 Web 系统

使用演示内存数据启动：

```bash
uvicorn main:app --reload
```

连接真实 Totem 数据库启动：

```bash
export TOTEM_USE_DEMO=0
export TOTEM_DATABASE=genealogy
export TOTEM_PORT=55432
uvicorn main:app --reload
```

如果 Totem 使用默认 5432 端口，可以不设置 `TOTEM_PORT`：

```bash
export TOTEM_USE_DEMO=0
export TOTEM_DATABASE=genealogy
uvicorn main:app --reload
```

启动后打开：

```text
http://127.0.0.1:8000
```

默认账号：

```text
admin / admin
```

---

## 8. 如果数据库名不叫 genealogy 会怎样

当前项目代码默认读取数据库 `genealogy`：

- `main.py` 默认 `TOTEM_DATABASE=genealogy`
- `load_db.py` 默认 `TOTEM_DATABASE=genealogy`
- `export_db.py` 默认 `TOTEM_DATABASE=genealogy`
- `README.md` 和本文件中的命令默认使用 `genealogy`

如果本地数据库名不是 `genealogy`，例如叫 `genealogy_db`，不会影响表结构本身，但所有连接命令必须统一改为该名字。

创建数据库：

```bash
/usr/local/totem/bin/createdb -p 55432 genealogy_db
```

初始化表：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy_db -f init_db.sql
```

导入数据时，`import_members.sql` 不依赖数据库名，只由 `tsql -d` 决定目标库：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy_db -f import_members.sql
```

启动 Web 时必须设置：

```bash
export TOTEM_USE_DEMO=0
export TOTEM_DATABASE=genealogy_db
export TOTEM_PORT=55432
uvicorn main:app --reload
```

如果忘记设置 `TOTEM_DATABASE`，Web 后端会继续尝试连接默认的 `genealogy`。当本地没有该库时，会出现连接失败；当本地有同名旧库时，界面可能显示旧库数据。这类问题排查时优先检查：

```bash
echo $TOTEM_DATABASE
echo $TOTEM_PORT
/usr/local/totem/bin/tsql -p "$TOTEM_PORT" -d "$TOTEM_DATABASE" -c '\dt'
```

建议团队成员统一使用 `genealogy`，除非有明确原因需要并行维护多个数据库。

---

## 9. 常见问题

### 9.1 `wsl: Failed to translate 'D:"'`

这是 WSL 在翻译某个 Windows 环境变量路径时的警告，通常不影响 Totem 或项目命令执行。如果命令最终返回成功，可以暂时忽略。

### 9.2 5432 端口被占用

启动日志中如果出现：

```text
could not bind IPv4 socket: Address already in use
```

说明 5432 被占用。可用 `55432` 启动 Totem：

```bash
/usr/local/totem/bin/totemctl -w -D /usr/local/totem/data -l /tmp/totem-55432.log -o '-p 55432' start
```

随后所有命令都带上 `-p 55432`，Web 启动前设置：

```bash
export TOTEM_PORT=55432
```

### 9.3 `\COPY` 语法报错

当前 Totem 的 `tsql` 使用旧式 COPY 元命令语法。本项目的导入文件使用：

```sql
\COPY members(...) FROM '/mnt/e/totemdb/project/members_load.csv' WITH CSV NULL ''
```

不要在该 `\COPY` 元命令末尾添加分号。
