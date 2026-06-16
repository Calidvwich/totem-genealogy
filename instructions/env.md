# 环境配置与运行指南

本文说明 Windows 本地 clone 项目后，如何在 WSL 中启动 TotemDB、初始化数据库、导入数据并运行 Web 系统。

默认配置：

- 项目目录：`/mnt/e/totemdb/project`
- WSL 发行版：`Ubuntu-18.04`
- Totem 安装目录：`/usr/local/totem`
- Totem 数据目录：`/usr/local/totem/data`
- 数据库名：`genealogy`
- 数据库用户：`totem`
- 数据库端口：`55432`
- Web 端口：`8000`

---

## 1. 进入 WSL

在 Windows PowerShell 或 CMD 中执行：

```powershell
wsl -d Ubuntu-18.04
```

进入项目目录：

```bash
cd /mnt/e/totemdb/project
```

如果项目位于其他位置，请同步修改 `config/startup/startup.local.json` 中的 `app.project_dir`。

---

## 2. 启动 TotemDB

TotemDB 不能以 root 身份运行，推荐使用 `totem` 用户启动：

```bash
sudo -iu totem
```

使用 55432 端口启动：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -o "-p 55432" -l /tmp/totem-55432.log start
```

验证连接：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT 1;"
```

如果提示数据库不存在，按下一节创建。

---

## 3. 创建数据库

```bash
/usr/local/totem/bin/createdb -p 55432 genealogy
```

验证：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "\dt"
```

空数据库还没有业务表是正常的。

---

## 4. 初始化表结构

回到项目目录：

```bash
cd /mnt/e/totemdb/project
```

执行：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -f init_db.sql
```

当前系统使用的主要表：

- `users`
- `genealogies`
- `collaborations`
- `members`
- `marriages`
- `member_photos`

说明：

- `member_photos` 用于以 sha256 存储上传图片内容。
- Totem 当前版本对 `CREATE TABLE IF NOT EXISTS` 和部分高级 PostgreSQL 语法支持有限，因此初始化脚本使用保守 SQL。
- 不建议在已有数据的库中重复执行 `init_db.sql`。

---

## 5. Python 环境

当前本地已使用项目内 `.venv` 运行。若需要重新创建：

```bash
sudo apt-get install python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

当前 `requirements.txt` 已按 Ubuntu 18.04 / Python 3.6 可安装版本固定，避免安装过新的 FastAPI 或 python-multipart。

---

## 6. 一键启动

Windows 中双击：

```text
start-genealogy.bat
```

它会：

1. 读取 `config/startup/startup.json` 或本地覆盖配置 `startup.local.json`。
2. 启动 TotemDB。
3. 检查数据库连接。
4. 后台启动 Uvicorn。
5. 检查 `http://127.0.0.1:8000` 是否可访问。

访问：

```text
http://localhost:8000
```

只检查数据库和配置，不启动 Web：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-genealogy.ps1 -CheckOnly
```

Web 后台日志：

```bash
tail -80 /tmp/totem-genealogy-uvicorn.log
```

---

## 7. 手动启动 Web

```bash
cd /mnt/e/totemdb/project
export TOTEM_USE_DEMO=0
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

默认账号：

```text
admin / 123456
test01 / 123456
```

普通用户也可以在登录页直接注册。

---

## 8. 生成和导入数据

生成 CSV：

```bash
cd /mnt/e/totemdb/project
.venv/bin/python generate_data.py
```

导入生成数据并清空现有族谱业务数据：

```bash
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
.venv/bin/python import.py generated --reset
```

也可以在 Web 页面点击“导入族谱”，选择：

- CSV 新建族谱。
- 导入生成数据。

生成数据约束：

- 默认约 105000 人。
- 默认 10 个族谱。
- 一个大族谱约 60000 人。
- 姓名格式为 `姓氏_代_编号`。
- 会生成婚姻数据。

---

## 9. 导出

Web 页面支持：

- 导出整个数据库。
- 多选导出族谱。
- 导出单个成员完整信息。

命令行也可使用：

```bash
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
.venv/bin/python export.py database
.venv/bin/python export.py clans 1 2 3
.venv/bin/python export.py member 100
```

默认输出目录：

```text
output/export/
```

---

## 10. 性能实验

Web 搜索区可选择：

- 普通模式：不启用成员搜索索引。
- 性能模式：启用成员搜索索引。

每次搜索会展示：

- 搜索是否成功。
- 搜索耗时。
- 内存峰值。
- 结果数量。

点击 `EXPLAIN` 会输出执行计划到：

```text
output/performance-test/
```

文件名格式为：

```text
YYYYMMDD-HHMMSS.txt
```

---

## 11. 如果数据库名不是 genealogy

代码默认连接 `genealogy`。如果本机数据库名不同，例如 `genealogy_db`，需要同步修改：

```bash
export TOTEM_DATABASE=genealogy_db
```

以及 `config/startup/startup.local.json`：

```json
{
  "totem": {
    "database": "genealogy_db"
  }
}
```

所有 `tsql -d genealogy` 命令也需要改成对应数据库名。

---

## 12. 常见问题

### 12.1 `wsl: Failed to translate 'D:"'`

这是 WSL 在翻译 Windows 环境变量路径时的警告。只要后续命令成功，一般可以忽略。

### 12.2 5432 端口被占用

日志出现：

```text
could not bind IPv4 socket: Address already in use
```

说明默认 5432 被占用，使用 55432：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -o "-p 55432" -l /tmp/totem-55432.log start
```

### 12.3 `localhost:8000` 拒绝连接

先检查 WSL 内部 Uvicorn 是否真的在运行：

```bash
ps -ef | grep "[u]vicorn main:app"
tail -80 /tmp/totem-genealogy-uvicorn.log
curl -I http://127.0.0.1:8000/
```

如果 WSL 内部 `curl` 返回 `200 OK`，但 Windows 浏览器访问 `http://localhost:8000` 被拒绝，说明问题通常不是 FastAPI，而是 WSL NAT 的 localhost 转发没有建立。可以在 Windows 中执行：

```powershell
wsl --shutdown
wsl -d Ubuntu-18.04
```

然后重新双击 `start-genealogy.bat`。

当前启动脚本会做两层检查：

1. WSL 内部 `http://127.0.0.1:8000/` 是否可访问。
2. Windows 侧 `http://127.0.0.1:8000/` 是否可访问。

如果第一步成功但第二步失败，脚本会明确提示这是 WSL localhost 转发问题，并给出 `wsl --shutdown` 的恢复建议。

另外，启动脚本默认会重启 pid 文件记录的旧 Uvicorn 进程，避免浏览器继续访问旧代码。如果确实想保留旧进程，可以手动执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-genealogy.ps1 -NoRestart
```

### 12.4 `\COPY` 语法报错

Totem 的 `tsql` 使用旧式 COPY 元命令语法，不要在 `\COPY` 行尾添加分号。当前主流程推荐使用 `import.py`，避免手写 COPY。

### 12.5 权限不足

Totem 数据库服务需要使用 `totem` 用户启动。如果普通用户启动出现 PID 文件或数据目录权限错误，先切换：

```bash
sudo -iu totem
```

再执行 `totemctl`。

---

## 13. 功能完成情况

系统主体功能已经实现。仍需人工补充的主要是实验报告材料：

- E-R 图。
- 关系模式和范式分析。
- 查询结果截图。
- 性能实验截图。
- 最终数据库导出文件。
