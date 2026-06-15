# 用途：把 FastAPI 路由、服务方法和主要数据库表对应起来，便于审计权限、读写影响和测试覆盖。

# API 路由与数据库操作映射

## 总览

FastAPI 应用定义在 `main.py`。真实 Totem 模式下主要通过 `TotemGenealogyService` 访问数据库；demo 模式下使用内存数据。权限检查主要由以下辅助函数完成：

- `require_actor()`：要求传入当前用户。
- `require_admin()`：只允许 `admin`。
- `require_clan_edit()`：要求族谱创建者或协作者。
- `require_clan_owner()`：只允许族谱创建者。

## 页面与静态资源

| 方法 | 路由 | 处理函数 | 主要行为 | 读写 |
| --- | --- | --- | --- | --- |
| GET | `/` | `index()` | 返回前端 HTML | 只读 |
| static | `/resources/*` | `StaticFiles` | 读取静态资源，包含默认头像 | 只读 |

## 用户与登录

| 方法 | 路由 | 处理函数 | Service 方法 | 主要表 | 权限 | 读写 |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/login` | `login()` | `authenticate()` | `users` | 无 | 读；旧明文密码会被升级为哈希 |
| GET | `/api/users` | `list_users()` | `users()` | `users` | 无 | 只读 |
| GET | `/api/users/{user_id}/detail` | `user_detail()` | `user_detail()` | `users`, `genealogies`, `collaborations` | 无 | 只读 |
| POST | `/api/users` | `create_user()` | `create_user()` | `users` | admin | 写 |
| PUT | `/api/users/{user_id}` | `update_user()` | `update_user()` | `users` | admin | 写 |
| DELETE | `/api/users/{user_id}` | `delete_user()` | `delete_user()` | `users`, `collaborations`, `genealogies` | admin | 写 |

审计关注：

- `/api/login` 在发现旧格式密码时会更新密码哈希，不是纯只读。
- 管理用户依赖 `current_user_id=admin` 查询参数，前端负责传递当前用户。

## 族谱与协作

| 方法 | 路由 | 处理函数 | Service 方法 | 主要表 | 权限 | 读写 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/clans` | `list_clans()` | `clans()` | `genealogies`, `users`, `collaborations` | 无 | 只读 |
| POST | `/api/clans` | `create_clan()` | `create_clan()` | `genealogies`, `collaborations`, `users` | 登录用户 | 写 |
| PUT | `/api/clans/{clan_id}` | `update_clan()` | `update_clan()` | `genealogies` | 创建者 | 写 |
| DELETE | `/api/clans/{clan_id}` | `delete_clan()` | `delete_clan()` | `genealogies`, `collaborations`, `members`, `marriages` | 创建者 | 写 |
| GET | `/api/clans/{clan_id}/collaborators` | `list_collaborators()` | `collaborators()` | `collaborations`, `users` | 无 | 只读 |
| GET | `/api/clans/{clan_id}/permission` | `clan_permission()` | `clan_permission()` | `users`, `genealogies`, `collaborations` | 登录用户参数 | 只读 |
| POST | `/api/collaborations` | `grant_collaboration()` | `grant_collaboration()` | `collaborations`, `users`, `genealogies` | 创建者 | 写 |
| DELETE | `/api/collaborations` | `revoke_collaboration()` | `revoke_collaboration()` | `collaborations`, `users`, `genealogies` | 创建者 | 写 |
| POST | `/api/invitations` | `invite()` | `grant_collaboration()` | `collaborations`, `users` | 创建者 | 写 |

审计关注：

- 删除族谱会删除成员、婚姻、协作关系，属于高影响操作。
- 创建者也会被写入 `collaborations`，用于统一编辑权限判断。

## 成员与头像

| 方法 | 路由 | 处理函数 | Service 方法 | 主要表 | 权限 | 读写 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/dashboard` | `dashboard()` | `dashboard()` | `members` | 无 | 只读 |
| GET | `/api/members` | `list_members()` | `members()` | `members` | 无 | 只读 |
| GET | `/api/members/search-performance` | `search_members_with_metrics()` | `measured_member_search()` | `members` | 无 | 可能创建或删除索引 |
| GET | `/api/members/{member_id}/detail` | `member_detail()` | `member_detail()` | `members`, `genealogies`, `marriages` | 无 | 只读 |
| POST | `/api/members` | `create_member()` | `create_member()` | `members`, `marriages` | 可编辑 | 写 |
| PUT | `/api/members/{member_id}` | `update_member()` | `update_member()` | `members`, `marriages` | 可编辑 | 写 |
| POST | `/api/members/{member_id}/photo` | `upload_member_photo()` | `update_member_photo_hash()` | `members`, `member_photos` | 可编辑 | 写 |
| GET | `/api/members/{member_id}/photo` | `get_member_photo()` | `member_photo()` | `members`, `member_photos`, `resources/defaultpic.jpg` | 无 | 只读 |
| DELETE | `/api/members/{member_id}` | `delete_member()` | `delete_member()` | `members`, `marriages` | 可编辑 | 写 |
| GET | `/api/tree` | `tree()` | `tree()` | `members` | 无 | 只读 |
| GET | `/api/members/{member_id}/ancestors` | `ancestors()` | `ancestors()` | `members` | 无 | 只读 |
| GET | `/api/members/{member_id}/relationship` | `relationship()` | `relationship_path()` | `members` | 无 | 只读 |

审计关注：

- `/api/members/search-performance` 是 GET，但会根据 `performance_mode` 调整索引，不应归类为只读 smoke endpoint。
- 上传头像会把图片内容 base64 存入 `member_photos`，并更新 `members.id_pic`。
- 默认头像依赖 `resources/defaultpic.jpg`，不要修改该文件。

## 婚姻

| 方法 | 路由 | 处理函数 | Service 方法 | 主要表 | 权限 | 读写 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/members/{member_id}/marriages` | `list_member_marriages()` | `member_marriages()` | `marriages`, `members` | 登录用户 | 只读 |
| POST | `/api/marriages` | `create_marriage()` | `create_marriage()` | `marriages`, `members` | 可编辑 | 写 |
| PUT | `/api/marriages/{marriage_id}/divorce` | `set_marriage_divorce()` | `set_divorce()` | `marriages` | 可编辑 | 写 |
| DELETE | `/api/marriages/{marriage_id}` | `delete_marriage()` | `delete_marriage()` | `marriages` | 可编辑 | 写 |

审计关注：

- 应用层检查同族谱、不能与自己结婚、年份顺序和婚姻重叠。
- 数据库层没有外键和唯一约束，外部导入仍需只读 SQL 校验。

## 导入与导出

| 方法 | 路由 | 处理函数 | 脚本/Service | 主要表 | 权限 | 读写 |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/import/clan-csv` | `import_clan_from_csv()` | `import.py::import_clan_csv()` | `genealogies`, `collaborations`, `members`, `marriages` | 登录用户 | 写 |
| POST | `/api/import/generated` | `import_generated()` | `import.py::import_generated_data(reset=True)` | `genealogies`, `collaborations`, `members`, `marriages` | admin | 清空后写 |
| POST | `/api/export/database` | `export_database()` | `export.py::export_database()` | 多表 | admin | 读数据库，写导出文件 |
| POST | `/api/export/clans` | `export_clans()` | `export.py::export_clans()` | 多表 | admin 或可编辑 | 读数据库，写导出文件 |
| POST | `/api/export/members/{member_id}` | `export_member()` | `export.py::export_member()` | 多表 | admin 或可编辑 | 读数据库，写导出文件 |

审计关注：

- `/api/import/generated` 会重置族谱业务数据，只能在测试库使用。
- 导出接口会写 `output/export`，不是数据库写入，但会产生本地文件。

## 业务查询

| 方法 | 路由 | 处理函数 | 主要表 | 读写 |
| --- | --- | --- | --- | --- |
| GET | `/api/query/spouse_children` | `query_spouse_children()` | `members`, `marriages` | 只读 |
| GET | `/api/query/longevity` | `query_longevity()` | `members` | 只读 |
| GET | `/api/query/singles` | `query_singles()` | `members` | 只读 |
| GET | `/api/query/early_birth` | `query_early_birth()` | `members` | 只读 |
| GET | `/api/query/great_grandchildren` | `query_great_grandchildren()` | `members` | 只读 |

审计关注：

- 这些接口多数在 Python 层计算，适合用手工测试验证边界数据。
- 对真实数据库性能敏感的查询可结合性能说明，但不要在 smoke test 中开启会改索引的模式。

## Smoke test 推荐覆盖

安全的只读 API smoke 范围：

- `GET /`
- `GET /api/clans`
- `GET /api/dashboard`
- `GET /api/members?clan_id=1`
- `GET /api/tree?clan_id=1`

不建议放入自动 smoke 的接口：

- 任何 POST、PUT、DELETE。
- `/api/login`，因为可能升级旧密码哈希。
- `/api/members/search-performance?performance_mode=true`，因为可能创建索引。
- 导入接口和导出接口，导入会改数据库，导出会写本地文件。
