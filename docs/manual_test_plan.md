# 用途：提供不会误伤主功能的数据安全测试计划，区分只读检查、demo 模式、真实 Totem 测试和高影响导入测试。

# 手工测试计划

## 测试原则

- 先用只读检查确认环境，再测试会写数据库的功能。
- 不在生产或唯一数据副本上运行 `load_db.py`、`import.py generated`、`/api/import/generated`。
- 不修改 `resources/` 和 `resources/defaultpic.jpg`。
- 每次真实 Totem 测试前确认 `TOTEM_DATABASE`、`TOTEM_PORT`、`TOTEM_USE_DEMO`。

## 只读本地检查

在项目根目录执行：

```bash
python scripts/smoke_check.py
```

预期：

- 必要文件存在。
- `scripts/schema_readonly_check.sql` 通过只读关键字检查。
- `main.py` 中关键路由存在。
- `init_db.sql` 中关键表存在。

如果 Web 已启动，可增加只读 API 检查：

```bash
python scripts/smoke_check.py --base-url http://127.0.0.1:8000
```

预期：

- `/`、`/api/clans`、`/api/dashboard`、`/api/members?clan_id=1`、`/api/tree?clan_id=1` 返回 2xx。
- 不会触发 POST、PUT、DELETE。

## 只读数据库一致性检查

确认连接真实 Totem 测试库后执行：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -f scripts/schema_readonly_check.sql
```

也可以通过 smoke 脚本调用：

```bash
TOTEM_PORT=55432 TOTEM_DATABASE=genealogy python scripts/smoke_check.py --run-sql
```

预期：

- 行数概览有输出。
- 异常检查项没有返回数据，或返回的数据能被解释为已知测试数据问题。

## Demo 模式测试

启动：

```bash
uvicorn main:app --reload
```

浏览器访问：

```text
http://127.0.0.1:8000
```

建议测试：

- 使用页面默认账号登录。
- 查看族谱列表。
- 查看成员列表、成员详情、树形图。
- 新增一个测试成员，再编辑姓名或简介。
- 查询祖先、亲属关系、配偶子女。

注意：

- demo 模式使用内存数据，刷新服务后数据会重置。
- demo 模式通过并不代表真实 Totem 连接正常。

## 真实 Totem 模式测试

启动前设置：

```bash
export TOTEM_USE_DEMO=0
export TOTEM_DATABASE=genealogy
export TOTEM_PORT=55432
uvicorn main:app --reload
```

先用命令确认数据库：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -c 'SELECT COUNT(*) AS users_count FROM users;'
/usr/local/totem/bin/tsql -p 55432 -d genealogy -c 'SELECT COUNT(*) AS members_count FROM members;'
```

建议测试：

- 登录后确认页面数据与数据库行数大致匹配。
- 创建新族谱，确认当前用户成为创建者和协作者。
- 新增成员，分别测试合法父母、父母跨族谱、父母性别不符、出生年份早于父母等场景。
- 建立婚姻，测试不能与自己结婚、配偶必须同族谱、时间区间不能重叠。
- 上传一张小图片，确认成员头像显示；删除测试数据前先确认不会影响课程演示数据。

## 权限测试

建议使用 `admin` 和一个普通测试用户：

- 普通用户不能管理用户。
- 普通用户不能修改非自己创建且未授权的族谱。
- 族谱创建者可以授权协作者。
- 协作者可以编辑成员，但不能删除整个族谱或管理协作者。
- 创建者不能从协作者列表撤销自己的创建者权限。

## 导入测试

仅在可重建的测试库执行。

CSV 新建族谱导入：

```bash
python import.py csv sample.csv --title 测试导入族谱 --surname 测
```

检查：

- 新增一条 `genealogies`。
- 新增成员均属于新族谱。
- 父母引用与婚姻关系可通过 `scripts/schema_readonly_check.sql` 检查。

生成数据导入：

```bash
python import.py generated --total 1000
```

风险：

- 默认会清空族谱、成员、婚姻和协作关系。
- Web 接口 `/api/import/generated` 同样会重置业务数据。

## 导出测试

导出会读取数据库并写入 `output/export`：

```bash
python export.py all
python export.py clans 1
python export.py member 1
```

检查：

- 生成 `manifest.json`。
- CSV 文件有表头和合理行数。
- 导出单成员时包含父母、子女、配偶、祖先等关联文件。

## 回归检查清单

每次提交前建议运行：

```bash
python -m py_compile scripts/smoke_check.py
python scripts/smoke_check.py
```

如连接真实库，再运行：

```bash
/usr/local/totem/bin/tsql -p 55432 -d genealogy -f scripts/schema_readonly_check.sql
```

通过标准：

- smoke 脚本退出码为 0。
- 只读 SQL 没有明显异常结果。
- 页面核心流程仍可打开和浏览。
