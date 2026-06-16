# 完整数据库导出与恢复说明

本文件夹保存了一份完整数据库导出。恢复时不需要迁移 SQL：先用当前项目的 `init_db.sql` 建立最新表结构，再用 `import_bundle.json` 恢复业务数据，导入脚本会自动重建对象-代理层。

## 文件内容

- `import_bundle.json`：可直接导入的完整恢复包。
- `manifest.json`：导出元信息。
- `users.csv`：用户数据。
- `genealogies.csv`：族谱数据。
- `collaborations.csv`：协作权限数据。
- `members.csv`：成员数据。
- `marriages.csv`：婚姻关系数据。
- `member_photos.csv`：成员照片数据，照片内容以 sha256 和 base64 形式存储。

## 恢复流程

先启动 TotemDB，并确认 `genealogy` 数据库可连接：

```bash
/usr/local/totem/bin/totemctl -D /usr/local/totem/data -o "-p 55432" -l /tmp/totem-55432.log start
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT 1;"
```

进入项目目录并初始化最新表结构：

```bash
cd /mnt/e/totemdb/project
. .venv/bin/activate
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -f init_db.sql
```

然后恢复完整导出：

```bash
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
python import.py restore fulldb/import_bundle.json --reset
```

`--reset` 会清空当前库中的用户、族谱、成员、婚姻、协作权限、照片以及对象代理数据，再恢复导出包内容。恢复完成后，`import.py` 会根据恢复后的业务表自动生成：

- `objects`
- `object_proxies`
- 各业务表中的 `object_id`

因此旧导出包可以直接用于当前对象-代理风格的新表结构。

## 恢复验证

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT COUNT(*) FROM members;"
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT object_type, COUNT(*) FROM objects GROUP BY object_type ORDER BY object_type;"
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -c "SELECT proxy_table, COUNT(*) FROM object_proxies GROUP BY proxy_table ORDER BY proxy_table;"
```

默认测试账号：

```text
admin / 123456
test01 / 123456
```
