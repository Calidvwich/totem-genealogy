import csv
import hashlib
import os
import subprocess
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from interface import render_app


APP_DIR = Path(__file__).resolve().parent
DATABASE_NAME = os.getenv("TOTEM_DATABASE", "genealogy")
TSQL_BIN = os.getenv("TOTEM_TSQL", "/usr/local/totem/bin/tsql")
TOTEM_PORT = os.getenv("TOTEM_PORT", "")
TOTEM_USER = os.getenv("TOTEM_USER", "totem")
USE_TOTEM = os.getenv("TOTEM_USE_DEMO", "1") not in {"1", "true", "TRUE", "yes"}


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1)
    password: str = Field(min_length=1)


class MemberIn(BaseModel):
    clan_id: int = 1
    name: str = Field(min_length=1, max_length=50)
    gender: str = "U"
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    father_id: Optional[int] = None
    mother_id: Optional[int] = None
    generation_num: Optional[int] = None
    bio: Optional[str] = ""


class MemberUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=50)
    gender: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    father_id: Optional[int] = None
    mother_id: Optional[int] = None
    generation_num: Optional[int] = None
    bio: Optional[str] = None


class InvitationIn(BaseModel):
    clan_id: int
    user_id: str = Field(min_length=1)


@dataclass
class User:
    id: int
    user_id: str
    password_hash: str
    username: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class Genealogy:
    clan_id: int
    title: str
    surname: str
    creator_id: int
    revised_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class Member:
    member_id: int
    clan_id: int
    name: str
    gender: str
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    father_id: Optional[int] = None
    mother_id: Optional[int] = None
    generation_num: Optional[int] = None
    bio: Optional[str] = ""
    id_pic: Optional[str] = None


def public_member(member: Member) -> Dict[str, Any]:
    data = member.__dict__.copy()
    data["gender_label"] = {"M": "男", "F": "女", "U": "未知"}.get(member.gender, "未知")
    return data


def merge_dict(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    data = base.copy()
    data.update(extra)
    return data


def dump_model(model: BaseModel, exclude_unset: bool = False) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=exclude_unset)
    return model.dict(exclude_unset=exclude_unset)


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


class TotemClient:
    def __init__(self, database: str = DATABASE_NAME, tsql_bin: str = TSQL_BIN, port: str = TOTEM_PORT, user: str = TOTEM_USER) -> None:
        self.database = database
        self.tsql_bin = tsql_bin
        self.port = port
        self.user = user

    def query(self, sql: str) -> List[Dict[str, str]]:
        command = [self.tsql_bin]
        if self.port:
            command.extend(["-p", self.port])
        if self.user:
            command.extend(["-U", self.user])
        command.extend(["-d", self.database, "-A", "-F", "\t", "-c", sql])
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
            timeout=15,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        lines = [line for line in completed.stdout.splitlines() if line and not line.startswith("(")]
        if not lines:
            return []
        reader = csv.DictReader(StringIO("\n".join(lines)), delimiter="\t")
        return list(reader)

    def execute(self, sql: str) -> None:
        command = [self.tsql_bin]
        if self.port:
            command.extend(["-p", self.port])
        if self.user:
            command.extend(["-U", self.user])
        command.extend(["-d", self.database, "-c", sql])
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
            timeout=15,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


class GenealogyService:
    def authenticate(self, user_id: str, password: str) -> Dict[str, Any]:
        raise NotImplementedError

    def users(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def clans(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def dashboard(self, clan_id: int) -> Dict[str, Any]:
        raise NotImplementedError

    def members(self, clan_id: int, q: str = "") -> List[Dict[str, Any]]:
        raise NotImplementedError

    def create_member(self, payload: MemberIn) -> Dict[str, Any]:
        raise NotImplementedError

    def update_member(self, member_id: int, payload: MemberUpdate) -> Dict[str, Any]:
        raise NotImplementedError

    def update_member_photo_hash(self, member_id: int, photo_hash: str) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_member(self, member_id: int) -> None:
        raise NotImplementedError

    def tree(self, clan_id: int, root_id: Optional[int] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def ancestors(self, member_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def relationship_path(self, source_id: int, target_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def invite(self, payload: InvitationIn) -> Dict[str, Any]:
        raise NotImplementedError


class DemoGenealogyService(GenealogyService):
    def __init__(self) -> None:
        self._users = {
            1: User(1, "admin", "123456", "管理员"),
            2: User(2, "editor", "editor", "协作者"),
        }
        self._marriages: Set[Tuple[int, int]] = set()
        self._clans = {1: Genealogy(1, "张氏示例族谱", "张", 1)}
        self._collaborations: Set[Tuple[int, int]] = {(1, 1)}
        self._members = {
            1: Member(1, 1, "张太公", "M", 1860, 1930, None, None, 1, "族谱源头人物。"),
            2: Member(2, 1, "李氏", "F", 1868, 1940, None, None, 1, "张太公配偶。"),
            3: Member(3, 1, "张伯仁", "M", 1892, 1960, 1, 2, 2, "二代长子。"),
            4: Member(4, 1, "张仲义", "M", 1898, 1968, 1, 2, 2, "二代次子。"),
            5: Member(5, 1, "王氏", "F", 1902, 1979, None, None, 2, "张伯仁配偶。"),
            6: Member(6, 1, "张明德", "M", 1928, 2001, 3, 5, 3, "三代成员。"),
            7: Member(7, 1, "张明珠", "F", 1932, None, 3, 5, 3, "三代成员。"),
            8: Member(8, 1, "陈氏", "F", 1930, None, None, None, 3, "张明德配偶。"),
            9: Member(9, 1, "张远山", "M", 1958, None, 6, 8, 4, "四代成员。"),
            10: Member(10, 1, "张远晴", "F", 1962, None, 6, 8, 4, "四代成员。"),
        }

    def authenticate(self, user_id: str, password: str) -> Dict[str, Any]:
        for user in self._users.values():
            if user.user_id == user_id and user.password_hash == password:
                return {"ok": True, "user": merge_dict(user.__dict__, {"password_hash": ""})}
        raise HTTPException(status_code=401, detail="账号或密码不正确")

    def users(self) -> List[Dict[str, Any]]:
        return [{k: v for k, v in user.__dict__.items() if k != "password_hash"} for user in self._users.values()]

    def clans(self) -> List[Dict[str, Any]]:
        return [clan.__dict__ for clan in self._clans.values()]

    def dashboard(self, clan_id: int) -> Dict[str, Any]:
        members = [m for m in self._members.values() if m.clan_id == clan_id]
        male = sum(1 for m in members if m.gender == "M")
        female = sum(1 for m in members if m.gender == "F")
        unknown = sum(1 for m in members if m.gender == "U")
        oldest = min((m for m in members if m.birth_year), key=lambda m: m.birth_year, default=None)
        return {
            "clan_id": clan_id,
            "total_members": len(members),
            "gender": {"M": male, "F": female, "U": unknown},
            "oldest": public_member(oldest) if oldest else None,
            "collaborators": len([c for c in self._collaborations if c[0] == clan_id]),
        }

    def members(self, clan_id: int, q: str = "") -> List[Dict[str, Any]]:
        keyword = q.strip().lower()
        rows = [m for m in self._members.values() if m.clan_id == clan_id]
        if keyword:
            rows = [m for m in rows if keyword in m.name.lower() or keyword in str(m.member_id)]
        return [public_member(m) for m in sorted(rows, key=lambda item: (item.generation_num or 999, item.member_id))]

    def create_member(self, payload: MemberIn) -> Dict[str, Any]:
        self._validate_gender(payload.gender)
        self._validate_years(payload.birth_year, payload.death_year)
        member_id = max(self._members) + 1 if self._members else 1
        member = Member(member_id=member_id, **dump_model(payload), id_pic=None)
        self._members[member_id] = member
        self._ensure_demo_marriage(member.father_id, member.mother_id)
        return public_member(member)

    def update_member(self, member_id: int, payload: MemberUpdate) -> Dict[str, Any]:
        member = self._find_member(member_id)
        changes = dump_model(payload, exclude_unset=True)
        if changes.get("gender") is not None:
            self._validate_gender(changes["gender"])
        birth_year = changes.get("birth_year", member.birth_year)
        death_year = changes.get("death_year", member.death_year)
        self._validate_years(birth_year, death_year)
        old_pair = self._parent_pair(member.father_id, member.mother_id)
        for key, value in changes.items():
            setattr(member, key, value)
        new_pair = self._parent_pair(member.father_id, member.mother_id)
        if old_pair != new_pair:
            self._cleanup_demo_marriage(old_pair)
            self._ensure_demo_marriage(member.father_id, member.mother_id)
        return public_member(member)

    def update_member_photo_hash(self, member_id: int, photo_hash: str) -> Dict[str, Any]:
        member = self._find_member(member_id)
        member.id_pic = photo_hash
        return public_member(member)

    def delete_member(self, member_id: int) -> None:
        member_to_delete = self._find_member(member_id)
        affected_pairs = [self._parent_pair(member_to_delete.father_id, member_to_delete.mother_id)]
        for member in self._members.values():
            if member.father_id == member_id:
                affected_pairs.append(self._parent_pair(member.father_id, member.mother_id))
                member.father_id = None
            if member.mother_id == member_id:
                affected_pairs.append(self._parent_pair(member.father_id, member.mother_id))
                member.mother_id = None
        del self._members[member_id]
        for pair in affected_pairs:
            self._cleanup_demo_marriage(pair)

    def tree(self, clan_id: int, root_id: Optional[int] = None) -> Dict[str, Any]:
        members = [m for m in self._members.values() if m.clan_id == clan_id]
        children: Dict[int, List[Member]] = {}
        for member in members:
            for parent_id in (member.father_id, member.mother_id):
                if parent_id:
                    children.setdefault(parent_id, []).append(member)

        roots = [self._members[root_id]] if root_id else [m for m in members if not m.father_id and not m.mother_id]

        def build(member: Member, seen: Optional[Set[int]] = None) -> Dict[str, Any]:
            seen = seen or set()
            if member.member_id in seen:
                return merge_dict(public_member(member), {"children": []})
            seen.add(member.member_id)
            branch = public_member(member)
            branch["children"] = [build(child, seen.copy()) for child in children.get(member.member_id, [])]
            return branch

        return {"roots": [build(root) for root in roots if root.clan_id == clan_id]}

    def ancestors(self, member_id: int) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        queue: Deque[Tuple[Optional[int], int]] = deque([(self._find_member(member_id).father_id, 1), (self._find_member(member_id).mother_id, 1)])
        seen: Set[int] = set()
        while queue:
            current_id, depth = queue.popleft()
            if not current_id or current_id in seen or current_id not in self._members:
                continue
            seen.add(current_id)
            member = self._members[current_id]
            result.append(merge_dict(public_member(member), {"generations_above": depth}))
            queue.append((member.father_id, depth + 1))
            queue.append((member.mother_id, depth + 1))
        return result

    def relationship_path(self, source_id: int, target_id: int) -> List[Dict[str, Any]]:
        self._find_member(source_id)
        self._find_member(target_id)
        graph: Dict[int, Set[int]] = {member_id: set() for member_id in self._members}
        for member in self._members.values():
            for parent_id in (member.father_id, member.mother_id):
                if parent_id and parent_id in self._members:
                    graph[member.member_id].add(parent_id)
                    graph[parent_id].add(member.member_id)

        queue: Deque[List[int]] = deque([[source_id]])
        seen = {source_id}
        while queue:
            path = queue.popleft()
            current = path[-1]
            if current == target_id:
                return [public_member(self._members[mid]) for mid in path]
            for next_id in sorted(graph.get(current, set())):
                if next_id not in seen:
                    seen.add(next_id)
                    queue.append(path + [next_id])
        return []

    def invite(self, payload: InvitationIn) -> Dict[str, Any]:
        user = next((u for u in self._users.values() if u.user_id == payload.user_id), None)
        if not user:
            raise HTTPException(status_code=404, detail="未找到该用户")
        if payload.clan_id not in self._clans:
            raise HTTPException(status_code=404, detail="未找到该族谱")
        self._collaborations.add((payload.clan_id, user.id))
        return {"ok": True, "message": f"已邀请 {user.username} 编辑族谱"}

    def _find_member(self, member_id: int) -> Member:
        member = self._members.get(member_id)
        if not member:
            raise HTTPException(status_code=404, detail="未找到成员")
        return member

    @staticmethod
    def _validate_years(birth_year: Optional[int], death_year: Optional[int]) -> None:
        if birth_year and death_year and death_year < birth_year:
            raise HTTPException(status_code=400, detail="死亡年份不能早于出生年份")

    @staticmethod
    def _validate_gender(gender: Optional[str]) -> None:
        if gender not in {"M", "F", "U"}:
            raise HTTPException(status_code=400, detail="性别只能是 M、F 或 U")

    @staticmethod
    def _parent_pair(father_id: Optional[int], mother_id: Optional[int]) -> Optional[Tuple[int, int]]:
        if father_id and mother_id and father_id != mother_id:
            return (int(father_id), int(mother_id))
        return None

    def _ensure_demo_marriage(self, father_id: Optional[int], mother_id: Optional[int]) -> None:
        pair = self._parent_pair(father_id, mother_id)
        if pair:
            self._marriages.add(pair)

    def _cleanup_demo_marriage(self, pair: Optional[Tuple[int, int]]) -> None:
        if not pair:
            return
        father_id, mother_id = pair
        has_common_child = any(
            member.father_id == father_id and member.mother_id == mother_id
            for member in self._members.values()
        )
        if not has_common_child:
            self._marriages.discard(pair)


class TotemGenealogyService(DemoGenealogyService):
    def __init__(self) -> None:
        super().__init__()
        self.client = TotemClient()

    def authenticate(self, user_id: str, password: str) -> Dict[str, Any]:
        try:
            rows = self.client.query(
                "SELECT id,user_id,username,created_at FROM users "
                f"WHERE user_id = {sql_literal(user_id)} AND password_hash = {sql_literal(password)} LIMIT 1;"
            )
            if not rows:
                raise HTTPException(status_code=401, detail="账号或密码不正确")
            return {"ok": True, "user": rows[0]}
        except HTTPException:
            raise
        except Exception:
            return super().authenticate(user_id, password)

    def users(self) -> List[Dict[str, Any]]:
        try:
            return self.client.query("SELECT id,user_id,username,created_at FROM users ORDER BY id;")
        except Exception:
            return super().users()

    def clans(self) -> List[Dict[str, Any]]:
        try:
            return self.client.query("SELECT clan_id,title,surname,revised_at,creator_id FROM genealogies ORDER BY clan_id;")
        except Exception:
            return super().clans()

    def dashboard(self, clan_id: int) -> Dict[str, Any]:
        try:
            total = self.client.query(f"SELECT COUNT(*) AS total FROM members WHERE clan_id = {sql_literal(clan_id)};")
            gender = self.client.query(
                f"SELECT gender, COUNT(*) AS count FROM members WHERE clan_id = {sql_literal(clan_id)} GROUP BY gender;"
            )
            oldest = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE clan_id = {sql_literal(clan_id)} AND birth_year IS NOT NULL ORDER BY birth_year ASC LIMIT 1;"
            )
            counts = {"M": 0, "F": 0, "U": 0}
            for row in gender:
                counts[row.get("gender") or "U"] = int(row.get("count") or 0)
            return {
                "clan_id": clan_id,
                "total_members": int(total[0]["total"]) if total else 0,
                "gender": counts,
                "oldest": oldest[0] if oldest else None,
                "collaborators": 0,
            }
        except Exception:
            return super().dashboard(clan_id)

    def members(self, clan_id: int, q: str = "") -> List[Dict[str, Any]]:
        try:
            where = [f"clan_id = {sql_literal(clan_id)}"]
            if q.strip():
                where.append(f"name LIKE {sql_literal('%' + q.strip() + '%')}")
            sql = (
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE {' AND '.join(where)} ORDER BY generation_num, member_id LIMIT 200;"
            )
            return self.client.query(sql)
        except Exception:
            return super().members(clan_id, q)

    def create_member(self, payload: MemberIn) -> Dict[str, Any]:
        try:
            self._validate_gender(payload.gender)
            self._validate_years(payload.birth_year, payload.death_year)
            next_id_rows = self.client.query("SELECT COALESCE(MAX(member_id), 0) + 1 AS member_id FROM members;")
            member_id = int(next_id_rows[0]["member_id"]) if next_id_rows else 1
            values = [
                member_id,
                payload.clan_id,
                payload.name,
                payload.gender,
                payload.birth_year,
                payload.death_year,
                payload.father_id,
                payload.mother_id,
                payload.generation_num,
                payload.bio,
                None,
            ]
            self.client.execute(
                "INSERT INTO members(member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic) "
                f"VALUES ({', '.join(sql_literal(value) for value in values)});"
            )
            self._ensure_parent_marriage(payload.clan_id, payload.father_id, payload.mother_id)
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE member_id = {sql_literal(member_id)};"
            )
            return rows[0]
        except Exception:
            return super().create_member(payload)

    def update_member(self, member_id: int, payload: MemberUpdate) -> Dict[str, Any]:
        try:
            changes = dump_model(payload, exclude_unset=True)
            if changes.get("gender") is not None:
                self._validate_gender(changes["gender"])
            if not changes:
                rows = self.members(1, str(member_id))
                return rows[0] if rows else super().update_member(member_id, payload)
            before = self._member_parent_row(member_id)
            old_pair = self._parent_pair_from_row(before)
            assignments = [f"{key} = {sql_literal(value)}" for key, value in changes.items()]
            self.client.execute(f"UPDATE members SET {', '.join(assignments)} WHERE member_id = {sql_literal(member_id)};")
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE member_id = {sql_literal(member_id)};"
            )
            if not rows:
                raise HTTPException(status_code=404, detail="未找到成员")
            new_pair = self._parent_pair_from_row(rows[0])
            if old_pair != new_pair:
                self._cleanup_parent_marriage(old_pair)
                self._ensure_parent_marriage(
                    self._optional_int(rows[0].get("clan_id")) or self._optional_int(before.get("clan_id")) or 1,
                    self._optional_int(rows[0].get("father_id")),
                    self._optional_int(rows[0].get("mother_id")),
                )
            return rows[0]
        except HTTPException:
            raise
        except Exception:
            return super().update_member(member_id, payload)

    def update_member_photo_hash(self, member_id: int, photo_hash: str) -> Dict[str, Any]:
        try:
            self.client.execute(f"UPDATE members SET id_pic = {sql_literal(photo_hash)} WHERE member_id = {sql_literal(member_id)};")
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE member_id = {sql_literal(member_id)};"
            )
            if not rows:
                raise HTTPException(status_code=404, detail="未找到成员")
            return rows[0]
        except HTTPException:
            raise
        except Exception:
            return super().update_member_photo_hash(member_id, photo_hash)

    def delete_member(self, member_id: int) -> None:
        try:
            pairs = self._affected_parent_pairs_for_delete(member_id)
            self.client.execute(f"UPDATE members SET father_id = NULL WHERE father_id = {sql_literal(member_id)};")
            self.client.execute(f"UPDATE members SET mother_id = NULL WHERE mother_id = {sql_literal(member_id)};")
            self.client.execute(f"DELETE FROM members WHERE member_id = {sql_literal(member_id)};")
            for pair in pairs:
                self._cleanup_parent_marriage(pair)
        except Exception:
            super().delete_member(member_id)

    def tree(self, clan_id: int, root_id: Optional[int] = None) -> Dict[str, Any]:
        try:
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE clan_id = {sql_literal(clan_id)} ORDER BY generation_num, member_id;"
            )
            return self._tree_from_rows(rows, clan_id, root_id)
        except Exception:
            return super().tree(clan_id, root_id)

    def ancestors(self, member_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic FROM members;"
            )
            members = {int(row["member_id"]): row for row in rows}
            if member_id not in members:
                raise HTTPException(status_code=404, detail="未找到成员")
            result: List[Dict[str, Any]] = []
            queue: Deque[Tuple[Optional[int], int]] = deque([
                (self._optional_int(members[member_id].get("father_id")), 1),
                (self._optional_int(members[member_id].get("mother_id")), 1),
            ])
            seen: Set[int] = set()
            while queue:
                current_id, depth = queue.popleft()
                if not current_id or current_id in seen or current_id not in members:
                    continue
                seen.add(current_id)
                row = members[current_id]
                result.append(merge_dict(row, {"generations_above": depth}))
                queue.append((self._optional_int(row.get("father_id")), depth + 1))
                queue.append((self._optional_int(row.get("mother_id")), depth + 1))
            return result
        except HTTPException:
            raise
        except Exception:
            return super().ancestors(member_id)

    def relationship_path(self, source_id: int, target_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic FROM members;"
            )
            members = {int(row["member_id"]): row for row in rows}
            if source_id not in members or target_id not in members:
                raise HTTPException(status_code=404, detail="未找到成员")
            graph: Dict[int, Set[int]] = {member_id: set() for member_id in members}
            for member_id, row in members.items():
                for parent_id in (self._optional_int(row.get("father_id")), self._optional_int(row.get("mother_id"))):
                    if parent_id and parent_id in members:
                        graph[member_id].add(parent_id)
                        graph[parent_id].add(member_id)
            queue: Deque[List[int]] = deque([[source_id]])
            seen = {source_id}
            while queue:
                path = queue.popleft()
                current = path[-1]
                if current == target_id:
                    return [members[mid] for mid in path]
                for next_id in sorted(graph[current]):
                    if next_id not in seen:
                        seen.add(next_id)
                        queue.append(path + [next_id])
            return []
        except HTTPException:
            raise
        except Exception:
            return super().relationship_path(source_id, target_id)

    def invite(self, payload: InvitationIn) -> Dict[str, Any]:
        try:
            rows = self.client.query(f"SELECT id,username FROM users WHERE user_id = {sql_literal(payload.user_id)} LIMIT 1;")
            if not rows:
                raise HTTPException(status_code=404, detail="未找到该用户")
            user_id = rows[0]["id"]
            exists = self.client.query(
                f"SELECT 1 FROM collaborations WHERE clan_id = {sql_literal(payload.clan_id)} AND user_id = {sql_literal(user_id)} LIMIT 1;"
            )
            if not exists:
                self.client.execute(
                    f"INSERT INTO collaborations(clan_id,user_id) VALUES ({sql_literal(payload.clan_id)}, {sql_literal(user_id)});"
                )
            return {"ok": True, "message": f"已邀请 {rows[0].get('username') or payload.user_id} 编辑族谱"}
        except HTTPException:
            raise
        except Exception:
            return super().invite(payload)

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value in {None, "", "NULL"}:
            return None
        return int(value)

    def _member_parent_row(self, member_id: int) -> Dict[str, Any]:
        rows = self.client.query(
            "SELECT member_id,clan_id,father_id,mother_id FROM members "
            f"WHERE member_id = {sql_literal(member_id)} LIMIT 1;"
        )
        if not rows:
            raise HTTPException(status_code=404, detail="未找到成员")
        return rows[0]

    def _parent_pair_from_row(self, row: Dict[str, Any]) -> Optional[Tuple[int, int]]:
        return self._parent_pair(self._optional_int(row.get("father_id")), self._optional_int(row.get("mother_id")))

    def _ensure_parent_marriage(self, clan_id: Optional[int], father_id: Optional[int], mother_id: Optional[int]) -> None:
        pair = self._parent_pair(father_id, mother_id)
        if not pair:
            return
        father_id, mother_id = pair
        existing = self.client.query(
            "SELECT marriage_id FROM marriages WHERE "
            f"clan_id = {sql_literal(clan_id)} AND "
            f"((spouse_a_id = {sql_literal(father_id)} AND spouse_b_id = {sql_literal(mother_id)}) "
            f"OR (spouse_a_id = {sql_literal(mother_id)} AND spouse_b_id = {sql_literal(father_id)})) LIMIT 1;"
        )
        if existing:
            return
        next_id_rows = self.client.query("SELECT COALESCE(MAX(marriage_id), 0) + 1 AS marriage_id FROM marriages;")
        marriage_id = int(next_id_rows[0]["marriage_id"]) if next_id_rows else 1
        marry_year = self._infer_marry_year(father_id, mother_id)
        self.client.execute(
            "INSERT INTO marriages(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year) "
            f"VALUES ({sql_literal(marriage_id)}, {sql_literal(clan_id)}, {sql_literal(father_id)}, "
            f"{sql_literal(mother_id)}, {sql_literal(marry_year)}, NULL);"
        )

    def _infer_marry_year(self, father_id: int, mother_id: int) -> Optional[int]:
        rows = self.client.query(
            "SELECT MIN(birth_year) AS first_child_birth FROM members WHERE "
            f"father_id = {sql_literal(father_id)} AND mother_id = {sql_literal(mother_id)} "
            "AND birth_year IS NOT NULL;"
        )
        first_birth = self._optional_int(rows[0].get("first_child_birth")) if rows else None
        return first_birth - 1 if first_birth else None

    def _cleanup_parent_marriage(self, pair: Optional[Tuple[int, int]]) -> None:
        if not pair:
            return
        father_id, mother_id = pair
        common_children = self.client.query(
            "SELECT 1 FROM members WHERE "
            f"father_id = {sql_literal(father_id)} AND mother_id = {sql_literal(mother_id)} LIMIT 1;"
        )
        if common_children:
            return
        self.client.execute(
            "DELETE FROM marriages WHERE "
            f"(spouse_a_id = {sql_literal(father_id)} AND spouse_b_id = {sql_literal(mother_id)}) "
            f"OR (spouse_a_id = {sql_literal(mother_id)} AND spouse_b_id = {sql_literal(father_id)});"
        )

    def _affected_parent_pairs_for_delete(self, member_id: int) -> List[Optional[Tuple[int, int]]]:
        pairs: List[Optional[Tuple[int, int]]] = []
        try:
            pairs.append(self._parent_pair_from_row(self._member_parent_row(member_id)))
        except HTTPException:
            return pairs
        child_rows = self.client.query(
            "SELECT father_id,mother_id FROM members WHERE "
            f"father_id = {sql_literal(member_id)} OR mother_id = {sql_literal(member_id)};"
        )
        for row in child_rows:
            pairs.append(self._parent_pair_from_row(row))
        return pairs

    def _tree_from_rows(self, rows: List[Dict[str, Any]], clan_id: int, root_id: Optional[int]) -> Dict[str, Any]:
        members = {int(row["member_id"]): row for row in rows if int(row["clan_id"]) == clan_id}
        children: Dict[int, List[Dict[str, Any]]] = {}
        for row in members.values():
            for parent_id in (self._optional_int(row.get("father_id")), self._optional_int(row.get("mother_id"))):
                if parent_id:
                    children.setdefault(parent_id, []).append(row)
        root_rows = [members[root_id]] if root_id and root_id in members else [
            row for row in members.values()
            if not self._optional_int(row.get("father_id")) and not self._optional_int(row.get("mother_id"))
        ]

        def build(row: Dict[str, Any], seen: Optional[Set[int]] = None) -> Dict[str, Any]:
            seen = seen or set()
            member_id = int(row["member_id"])
            if member_id in seen:
                return merge_dict(row, {"children": []})
            seen.add(member_id)
            return merge_dict(row, {"children": [build(child, seen.copy()) for child in children.get(member_id, [])]})

        return {"roots": [build(row) for row in root_rows]}


service: GenealogyService = TotemGenealogyService() if USE_TOTEM else DemoGenealogyService()

app = FastAPI(title="Totem 族谱管理系统", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/resources", StaticFiles(directory=APP_DIR / "resources"), name="resources")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render_app()


@app.post("/api/login")
def login(payload: LoginRequest) -> Dict[str, Any]:
    return service.authenticate(payload.user_id, payload.password)


@app.get("/api/users")
def list_users() -> List[Dict[str, Any]]:
    return service.users()


@app.get("/api/clans")
def list_clans() -> List[Dict[str, Any]]:
    return service.clans()


@app.get("/api/dashboard")
def dashboard(clan_id: int = 1) -> Dict[str, Any]:
    return service.dashboard(clan_id)


@app.get("/api/members")
def list_members(clan_id: int = 1, q: str = "") -> List[Dict[str, Any]]:
    return service.members(clan_id, q)


@app.post("/api/members", status_code=201)
def create_member(payload: MemberIn) -> Dict[str, Any]:
    return service.create_member(payload)


@app.put("/api/members/{member_id}")
def update_member(member_id: int, payload: MemberUpdate) -> Dict[str, Any]:
    return service.update_member(member_id, payload)


@app.post("/api/members/{member_id}/photo")
async def upload_member_photo(member_id: int, photo: UploadFile = File(...)) -> Dict[str, Any]:
    if photo.content_type and not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只能上传图片文件")

    digest = hashlib.sha256()
    total_size = 0
    while True:
        chunk = await photo.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        digest.update(chunk)

    if total_size == 0:
        raise HTTPException(status_code=400, detail="上传图片不能为空")

    photo_hash = digest.hexdigest()
    member = service.update_member_photo_hash(member_id, photo_hash)
    return {"ok": True, "member": member, "photo_sha256": photo_hash}


@app.delete("/api/members/{member_id}", status_code=204)
def delete_member(member_id: int) -> None:
    service.delete_member(member_id)


@app.get("/api/tree")
def tree(clan_id: int = 1, root_id: Optional[int] = None) -> Dict[str, Any]:
    return service.tree(clan_id, root_id)


@app.get("/api/members/{member_id}/ancestors")
def ancestors(member_id: int) -> List[Dict[str, Any]]:
    return service.ancestors(member_id)


@app.get("/api/members/{member_id}/relationship")
def relationship(member_id: int, target_id: int = Query(..., gt=0)) -> Dict[str, Any]:
    return {"path": service.relationship_path(member_id, target_id)}


@app.post("/api/invitations", status_code=201)
def invite(payload: InvitationIn) -> Dict[str, Any]:
    return service.invite(payload)

