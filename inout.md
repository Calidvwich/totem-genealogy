# 导入导出文件说明

本文说明当前系统导入、导出的文件内容、可直接导入的格式、重复数据处理规则和默认存储路径。

---

## 1. 输出目录结构

项目所有导入导出中间文件都放在：

```text
output/
```

当前包含三个子目录：

```text
output/import/             Web 上传导入文件的临时保存目录
output/export/             数据库、族谱、成员导出目录
output/performance-test/   EXPLAIN ANALYZE 性能实验输出
```

这些目录属于运行产物，已在 `.gitignore` 中忽略。

---

## 2. 导出类型

### 2.1 导出整个数据库

Web：

```text
导出族谱 -> 导出整个数据库
```

命令行：

```bash
export TOTEM_DATABASE=genealogy
export TOTEM_USER=totem
export TOTEM_PORT=55432
.venv/bin/python export.py all
```

默认输出：

```text
output/export/database_YYYYMMDD_HHMMSS/
```

目录内容：

```text
manifest.json
import_bundle.json
users.csv
genealogies.csv
collaborations.csv
members.csv
marriages.csv
member_photos.csv
```

其中：

- `manifest.json`：导出说明，供查看。
- `import_bundle.json`：可直接再次导入数据库的恢复包。
- `*.csv`：各表数据，供人工检查、报告或单独处理。

### 2.2 导出部分族谱

Web：

```text
导出族谱 -> 勾选族谱 -> 导出所选族谱
```

命令行：

```bash
.venv/bin/python export.py clans 1 2 3
```

默认输出：

```text
output/export/clans_YYYYMMDD_HHMMSS/
```

目录内容：

```text
manifest.json
import_bundle.json
users.csv
genealogies.csv
collaborations.csv
members.csv
marriages.csv
member_photos.csv
```

说明：

- `users.csv` 只包含被导出族谱的创建者和协作者。
- `member_photos.csv` 只包含导出成员实际引用的照片。
- `import_bundle.json` 可导入到另一个数据库中。

### 2.3 导出单个成员

Web：

```text
成员详情 -> 导出该对象
```

命令行：

```bash
.venv/bin/python export.py member 100
```

默认输出：

```text
output/export/member_100_YYYYMMDD_HHMMSS/
```

目录内容：

```text
manifest.json
member.csv
genealogy.csv
parents.csv
children.csv
marriages.csv
spouses.csv
ancestors.csv
member_photos.csv
```

注意：

- 单个成员导出是“对象信息导出”，不是数据库恢复包。
- 当前不会生成 `import_bundle.json`，不能直接作为整库或族谱导入。

---

## 3. 可直接导入的文件

当前可以直接导入数据库的导出文件是：

```text
import_bundle.json
```

该文件由以下导出功能自动生成：

- 导出整个数据库。
- 导出部分族谱。

文件格式：

```json
{
  "format": "totem-genealogy-import-bundle",
  "format_version": 1,
  "manifest": {
    "type": "database 或 clans",
    "database": "genealogy",
    "exported_at": "YYYY-MM-DDTHH:MM:SS",
    "files": ["users.csv", "genealogies.csv", "..."],
    "import_file": "import_bundle.json"
  },
  "tables": {
    "users": [],
    "genealogies": [],
    "collaborations": [],
    "members": [],
    "marriages": [],
    "member_photos": []
  }
}
```

`tables` 中保存的是可恢复的完整表数据，字段与数据库表一致。

---

## 4. 导入导出包

### 4.1 Web 导入

只有管理员可以导入导出包。

操作：

```text
导入族谱 -> 导入导出包 -> 选择 import_bundle.json
```

规则：

- Web 导入不会清空现有数据。
- 如果发现重复主键、重复账号或重复协作关系，会立即停止导入。
- 停止时会显示具体冲突原因。

适用场景：

- 将某些族谱导入到另一个不含冲突 ID 的数据库。
- 检查导出包是否完整。

### 4.2 命令行导入

不清空现有数据，遇重复停止：

```bash
.venv/bin/python import.py restore output/export/clans_YYYYMMDD_HHMMSS/import_bundle.json
```

整库恢复到空表，导入前清空全部相关表：

```bash
.venv/bin/python import.py restore output/export/database_YYYYMMDD_HHMMSS/import_bundle.json --reset
```

`--reset` 会清空：

```text
marriages
members
collaborations
genealogies
member_photos
users
```

然后再导入 bundle 中的数据。

注意：

- `--reset` 适合整库恢复，不适合把部分族谱合并进已有数据库。
- Web 页面当前不提供 `--reset`，避免误删现有数据库。

---

## 5. 重复数据处理规则

导入 `import_bundle.json` 前会先检查重复，任何一项冲突都会停止导入，不会继续写入。

检查内容：

### 5.1 文件内部重复

- `users.id`
- `users.user_id`
- `genealogies.clan_id`
- `collaborations(clan_id, user_id)`
- `members.member_id`
- `marriages.marriage_id`
- `member_photos.photo_sha256`

### 5.2 与当前数据库重复

- 数据库中已存在相同 `users.id`
- 数据库中已存在相同 `users.user_id`
- 数据库中已存在相同 `genealogies.clan_id`
- 数据库中已存在相同 `members.member_id`
- 数据库中已存在相同 `marriages.marriage_id`
- 数据库中已存在相同 `member_photos.photo_sha256`
- 数据库中已存在相同 `collaborations(clan_id, user_id)`

示例报错：

```text
导入停止，发现重复或无效数据：
- 数据库中已存在 users.id=1
- 数据库中已存在账号 user_id=admin
- 数据库中已存在 members.member_id=100
```

如果需要恢复整库，请使用命令行 `--reset`。

---

## 6. CSV 新建族谱导入

除导出包外，系统仍支持上传一个成员 CSV 来新建族谱。

Web：

```text
导入族谱 -> 成员 CSV -> 导入 CSV 新建族谱
```

命令行：

```bash
.venv/bin/python import.py csv members.csv --title "张氏导入族谱" --surname "张" --creator admin
```

CSV 至少需要：

```text
name
```

推荐字段：

```text
member_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic
```

字段说明：

- `member_id`：CSV 内部旧编号，用于父母字段映射；导入到数据库时会重新分配新 ID。
- `name`：成员姓名，必需。
- `gender`：`M`、`F` 或 `U`。
- `birth_year`：出生年。
- `death_year`：死亡年。
- `father_id`：CSV 内部旧父亲编号。
- `mother_id`：CSV 内部旧母亲编号。
- `generation_num`：世代。
- `bio`：简介。
- `id_pic`：照片 sha256，可为空。

CSV 导入会新建一个族谱，不会恢复用户、协作、照片内容，也不会保留原数据库中的成员 ID。

---

## 7. 生成数据导入

生成数据导入使用项目根目录中的三个文件：

```text
genealogies_load.csv
members_load.csv
marriages_load.csv
```

命令行：

```bash
.venv/bin/python import.py generated
```

默认会清空当前族谱、协作、成员和婚姻数据，然后导入生成数据。

如果不想清空：

```bash
.venv/bin/python import.py generated --append
```

注意：

- `--append` 下若有主键重复，TotemDB 会报错并停止。
- 生成数据导入不处理 `member_photos`。

---

## 8. 推荐使用方式

### 整库备份与恢复

导出：

```bash
.venv/bin/python export.py all
```

恢复到空表：

```bash
.venv/bin/python import.py restore output/export/database_YYYYMMDD_HHMMSS/import_bundle.json --reset
```

### 迁移部分族谱到另一个数据库

导出：

```bash
.venv/bin/python export.py clans 1 2
```

导入：

```bash
.venv/bin/python import.py restore output/export/clans_YYYYMMDD_HHMMSS/import_bundle.json
```

若目标库已有相同 ID 或账号，导入会停止。需要先换一个空库，或在导出/导入前规划 ID。

### 从外部成员表新建族谱

```bash
.venv/bin/python import.py csv members.csv --title "导入族谱" --surname "张"
```
