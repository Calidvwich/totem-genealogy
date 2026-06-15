# 族谱管理系统（TotemDB 版）

本项目是基于 TotemDB、FastAPI 和 Uvicorn 的族谱管理系统。项目代码位于 `project/` 目录，数据库默认使用 WSL 中的 TotemDB 实例，数据库名为 `genealogy`。

默认测试环境：

- Windows + WSL `Ubuntu-18.04`
- Totem 安装目录：`/usr/local/totem`
- Totem 数据目录：`/usr/local/totem/data`
- Totem 端口：`55432`
- 项目数据库：`genealogy`
- Web 地址：`http://localhost:8000`

默认账号：

- 管理员：`admin / 123456`
- 普通测试账号：`test01 / 123456`

`resources/defaultpic.jpg` 是系统默认头像，请保留。

---

## 快速启动

推荐在 Windows 中直接双击：

```text
start-genealogy.bat
```

启动参数位于：

```text
config/startup/startup.json
```

如果本机 WSL 用户、端口、项目路径不同，复制一份本地配置：

```powershell
copy config\startup\startup.json config\startup\startup.local.json
```

脚本会优先读取 `startup.local.json`。该文件已加入 `.gitignore`，不会提交到仓库。

---

## 手动启动

启动 TotemDB：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -o "-p 55432" -l /tmp/totem-55432.log start
```

验证数据库：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT 1;"
```

启动 Web：

```bash
cd /mnt/e/totemdb/project
export TOTEM_USE_DEMO=0
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 已实现功能

- 登录、登出、普通用户注册。
- 管理员用户管理：查看用户详情、新建、修改、删除用户。
- 密码以 PBKDF2-SHA256 哈希存储，旧明文密码可迁移。
- 族谱管理：新建、修改、删除、查看协作者。
- 协作权限：族谱创建者可授权/撤销其他用户编辑权限。
- 成员管理：新建、修改、删除、详情查看、照片上传。
- 默认头像：未上传照片时显示 `resources/defaultpic.jpg`。
- 照片存储：图片内容以 sha256 为键存入数据库，不写入本地文件。
- 父母/子女关系：编辑成员时可按姓名选择父母或子女；重名时要求输入 ID 确认。
- 父母校验：父亲必须为男性，母亲必须为女性，父母与子女必须属于同一族谱。
- 婚姻管理：父母共同拥有子女时自动生成婚姻关系；移除共同子女关系后会移除无共同子女的自动婚姻关系。
- 树形展示：支持族谱树可视化、缩放、重置视图。
- 数据概览：全库或当前族谱的成员数、男女比例扇形图、最长辈成员。
- 搜索：模糊搜索成员，展示是否成功、耗时、内存、结果数量。
- 性能模式：可选择普通模式和索引模式。
- EXPLAIN：可导出搜索查询的 `EXPLAIN ANALYZE` 到 `output/performance-test/`。
- 导入：支持 CSV 新建族谱导入，也支持用生成脚本批量导入。
- 导出：支持导出全库、多个族谱、单个成员完整信息。

---

## 数据规模与生成

`generate_data.py` 可生成约 105000 条成员数据，默认生成 10 个族谱，其中一个大族谱约 60000 人。

数据生成约束：

- 父母出生年份 < 结婚年份 < 子女出生年份 < 离婚年份（若有） < 父母死亡年份（若有）。
- 父母同一时间只能与一个人存在婚姻关系。
- 父亲必须为男性，母亲必须为女性。
- 父母离婚后，已出生且未删除的子女关系仍保持。
- 成员命名格式为 `姓氏_代_编号`，例如 `张_1_1`。

---

## 目录说明

```text
main.py                         FastAPI 后端与业务服务
interface.py                    单页 Web 界面
init_db.sql                     初始化表结构
generate_data.py                大规模测试数据生成
import.py                       导入 CSV、生成数据或 import_bundle.json
export.py                       导出数据库、族谱、成员和可恢复导入包
logsave.py                      静默记录错误日志和用户操作日志
load_db.py                      兼容旧流程的数据导入脚本
migrate_passwords.py            明文密码迁移脚本
ensure_test_user.py             测试账号修复脚本
instructions/                   项目说明文档目录（环境、查询、导入导出、索引、待办等）
instructions/env.md             环境配置说明
instructions/inout.md           导入导出文件格式与路径说明
instructions/explain.md         索引设计与性能模式说明
instructions/queries.md         查询需求与 SQL 说明
instructions/property.md        数据库属性与设计说明
instructions/todo.md            需求清单与完成情况
config/startup/startup.json     一键启动参数
scripts/start-genealogy.ps1     一键启动脚本
output/import/                  上传导入中转目录
output/export/                  导出结果
output/performance-test/        EXPLAIN 输出
fulldb/                         当前完整数据库导出与恢复说明
log/errorlog.txt                错误/崩溃日志，本地运行生成
log/userlog/                    用户单次登录操作日志，本地运行生成
resources/defaultpic.jpg        默认头像
```

`references/` 是旧项目参考代码，已被 `.gitignore` 忽略。

---

## 仍需补充

系统功能主体已实现。剩余工作主要是课程提交材料与验证材料：

- 绘制最终 E-R 图。
- 补充关系模式、3NF/BCNF 分析到报告。
- 运行并截图保存核心查询结果。
- 运行并截图保存性能模式、EXPLAIN 对比结果。
- 整理最终数据库导出文件。
- 对 10 万级数据做一轮完整 UI 回归测试。
