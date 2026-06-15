# 完整数据库导出与恢复说明

本文件夹是当前 `genealogy` 数据库的完整导出，导出时间见 `manifest.json`。

## 文件内容

- `import_bundle.json`：完整可恢复导入包，推荐使用这个文件直接导入。
- `manifest.json`：导出元信息，记录导出类型、数据库名、导出时间和包含的文件。
- `users.csv`：用户表。
- `genealogies.csv`：族谱表。
- `collaborations.csv`：协作权限表。
- `members.csv`：成员表。
- `marriages.csv`：婚姻关系表。
- `member_photos.csv`：成员照片表，照片内容以 sha256 和 base64 形式存储。

当前导出规模：

- 用户：3
- 族谱：11
- 协作权限：12
- 成员：105004
- 婚姻关系：16183
- 成员照片：0

## 直接恢复到数据库

先启动 TotemDB，并确认 `genealogy` 数据库存在：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -o "-p 55432" -l /tmp/totem-55432.log start
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT 1;"
```

进入项目目录：

```bash
cd /mnt/e/totemdb/project
. .venv/bin/activate
```

如果是空数据库，先初始化表结构：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -f init_db.sql
```

然后执行完整恢复：

```bash
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
python import.py restore fulldb/import_bundle.json --reset
```

`--reset` 会先清空以下表，再导入本导出包：

- `users`
- `genealogies`
- `collaborations`
- `members`
- `marriages`
- `member_photos`

因此它适合完整替换数据库内容。如果不希望覆盖当前数据库，可以去掉 `--reset`：

```bash
python import.py restore fulldb/import_bundle.json
```

不带 `--reset` 时，如果数据库中已经存在相同用户、族谱 ID、成员 ID、婚姻 ID、照片 sha256 或协作关系，导入会停止并输出重复原因。

## 恢复后验证

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT COUNT(*) FROM members;"
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT COUNT(*) FROM marriages;"
```

也可以启动 Web 系统后访问：

```text
http://localhost:8000
```

默认测试账号：

```text
admin / 123456
test01 / 123456
```
