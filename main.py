import csv
import base64
import importlib.util
import hmac
import hashlib
import os
import secrets
import subprocess
import time
import tracemalloc
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from interface import render_app
from logsave import log_error, log_exception, log_user_action, start_user_log


APP_DIR = Path(__file__).resolve().parent
DATABASE_NAME = os.getenv("TOTEM_DATABASE", "genealogy")
TSQL_BIN = os.getenv("TOTEM_TSQL", "/usr/local/totem/bin/tsql")
TOTEM_PORT = os.getenv("TOTEM_PORT", "")
TOTEM_USER = os.getenv("TOTEM_USER", "totem")
USE_TOTEM = os.getenv("TOTEM_USE_DEMO", "1") not in {"1", "true", "TRUE", "yes"}
PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 150000
DEFAULT_ADMIN_PASSWORD_HASH = (
    "pbkdf2_sha256$150000$oIG0zKga4xpBMJ9KI7bAOg$3TjiTzurVc75Ql8+C5hQnSf7w5O9WK3UHcntJqJY6us"
)
MEMBER_PERFORMANCE_INDEXES = [
    ("idx_members_clan", "CREATE INDEX idx_members_clan ON members(clan_id)"),
    ("idx_members_name", "CREATE INDEX idx_members_name ON members(name)"),
    ("idx_members_clan_name", "CREATE INDEX idx_members_clan_name ON members(clan_id, name)"),
    ("idx_members_clan_order", "CREATE INDEX idx_members_clan_order ON members(clan_id, generation_num, member_id)"),
    ("idx_members_father", "CREATE INDEX idx_members_father ON members(father_id)"),
    ("idx_members_mother", "CREATE INDEX idx_members_mother ON members(mother_id)"),
]
MEMBER_INDEXES_TO_DROP = MEMBER_PERFORMANCE_INDEXES + [
    ("idx_members_birth", ""),
    ("idx_members_gender", ""),
]


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserIn(BaseModel):
    user_id: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=1, max_length=72)
    username: Optional[str] = Field(default="", max_length=50)


class UserUpdate(BaseModel):
    password: Optional[str] = Field(default=None, min_length=1, max_length=72)
    username: Optional[str] = Field(default=None, max_length=50)


class GenealogyIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    surname: Optional[str] = Field(default="", max_length=20)
    creator_user_id: Optional[str] = Field(default="admin", min_length=1)


class GenealogyUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=100)
    surname: Optional[str] = Field(default=None, max_length=20)


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


class CollaborationIn(BaseModel):
    clan_id: int
    user_id: str = Field(min_length=1)


class MarriageIn(BaseModel):
    member_id: int
    spouse_id: Optional[int] = None
    spouse_name: Optional[str] = Field(default=None, max_length=50)
    marry_year: Optional[int] = None
    divorce_year: Optional[int] = None


class MarriageDivorceIn(BaseModel):
    divorce_year: Optional[int] = None


class ExportClansRequest(BaseModel):
    clan_ids: List[int]


class PerformanceExplainRequest(BaseModel):
    q: str = Field(min_length=1)
    clan_id: int = 0
    performance_mode: bool = False


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


def is_password_hash(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PASSWORD_HASH_ALGORITHM + "$")


def hash_password(password: str) -> str:
    salt = secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    )
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return "{}${}${}${}".format(PASSWORD_HASH_ALGORITHM, PASSWORD_HASH_ITERATIONS, salt, encoded)


def verify_password(password: str, stored_hash: str) -> bool:
    if not is_password_hash(stored_hash):
        return hmac.compare_digest(password, stored_hash or "")
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
        if algorithm != PASSWORD_HASH_ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        actual = base64.b64encode(digest).decode("ascii").rstrip("=")
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


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

    def user_detail(self, user_id: int) -> Dict[str, Any]:
        raise NotImplementedError

    def create_user(self, payload: UserIn) -> Dict[str, Any]:
        raise NotImplementedError

    def update_user(self, user_id: int, payload: UserUpdate) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_user(self, user_id: int) -> None:
        raise NotImplementedError

    def clans(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def create_clan(self, payload: GenealogyIn) -> Dict[str, Any]:
        raise NotImplementedError

    def update_clan(self, clan_id: int, payload: GenealogyUpdate) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_clan(self, clan_id: int) -> None:
        raise NotImplementedError

    def collaborators(self, clan_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def grant_collaboration(self, payload: CollaborationIn) -> Dict[str, Any]:
        raise NotImplementedError

    def revoke_collaboration(self, payload: CollaborationIn) -> Dict[str, Any]:
        raise NotImplementedError

    def dashboard(self, clan_id: Optional[int]) -> Dict[str, Any]:
        raise NotImplementedError

    def members(self, clan_id: int, q: str = "") -> List[Dict[str, Any]]:
        raise NotImplementedError

    def member_detail(self, member_id: int) -> Dict[str, Any]:
        raise NotImplementedError

    def create_member(self, payload: MemberIn) -> Dict[str, Any]:
        raise NotImplementedError

    def update_member(self, member_id: int, payload: MemberUpdate) -> Dict[str, Any]:
        raise NotImplementedError

    def update_member_photo_hash(self, member_id: int, photo_hash: str, content: bytes = b"", content_type: str = "image/jpeg") -> Dict[str, Any]:
        raise NotImplementedError

    def member_photo(self, member_id: int) -> Optional[Tuple[bytes, str]]:
        raise NotImplementedError

    def delete_member(self, member_id: int) -> None:
        raise NotImplementedError

    def tree(self, clan_id: int, root_id: Optional[int] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def ancestors(self, member_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def relationship_path(self, source_id: int, target_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def member_marriages(self, member_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def create_marriage(self, payload: MarriageIn) -> Dict[str, Any]:
        raise NotImplementedError

    def set_divorce(self, marriage_id: int, payload: MarriageDivorceIn) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_marriage(self, marriage_id: int) -> None:
        raise NotImplementedError

    def invite(self, payload: InvitationIn) -> Dict[str, Any]:
        raise NotImplementedError

    def clan_permission(self, clan_id: int, user_id: str) -> Dict[str, bool]:
        raise NotImplementedError


class DemoGenealogyService(GenealogyService):
    def __init__(self) -> None:
        self._users = {
            1: User(1, "admin", DEFAULT_ADMIN_PASSWORD_HASH, "管理员"),
            2: User(2, "editor", hash_password("editor"), "协作者"),
            3: User(3, "test01", hash_password("123456"), "测试用户"),
        }
        self._marriages: Set[Tuple[int, int]] = set()
        self._photo_blobs: Dict[str, Tuple[bytes, str]] = {}
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
            if user.user_id == user_id and verify_password(password, user.password_hash):
                if not is_password_hash(user.password_hash):
                    user.password_hash = hash_password(password)
                return {"ok": True, "user": merge_dict(user.__dict__, {"password_hash": ""})}
        raise HTTPException(status_code=401, detail="账号或密码不正确")

    def users(self) -> List[Dict[str, Any]]:
        return [{k: v for k, v in user.__dict__.items() if k != "password_hash"} for user in self._users.values()]

    def user_detail(self, user_id: int) -> Dict[str, Any]:
        user = self._users.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="未找到用户")
        owned = []
        collaborated = []
        for clan in self.clans():
            if int(clan.get("creator_id") or 0) == user_id:
                owned.append(clan)
            elif (int(clan.get("clan_id") or 0), user_id) in self._collaborations:
                collaborated.append(clan)
        return {
            "user": {k: v for k, v in user.__dict__.items() if k != "password_hash"},
            "owned_clans": owned,
            "collaborated_clans": collaborated,
        }

    def create_user(self, payload: UserIn) -> Dict[str, Any]:
        if any(user.user_id == payload.user_id for user in self._users.values()):
            raise HTTPException(status_code=409, detail="账号已存在")
        user_id = max(self._users) + 1 if self._users else 1
        user = User(user_id, payload.user_id, hash_password(payload.password), payload.username or payload.user_id)
        self._users[user_id] = user
        return {k: v for k, v in user.__dict__.items() if k != "password_hash"}

    def update_user(self, user_id: int, payload: UserUpdate) -> Dict[str, Any]:
        user = self._users.get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="未找到用户")
        changes = dump_model(payload, exclude_unset=True)
        if "username" in changes:
            user.username = changes["username"] or user.user_id
        if "password" in changes and changes["password"]:
            user.password_hash = hash_password(changes["password"])
        return {k: v for k, v in user.__dict__.items() if k != "password_hash"}

    def delete_user(self, user_id: int) -> None:
        if user_id not in self._users:
            raise HTTPException(status_code=404, detail="未找到用户")
        if any(clan.creator_id == user_id for clan in self._clans.values()):
            raise HTTPException(status_code=400, detail="该用户仍是族谱创建者，不能删除")
        del self._users[user_id]
        self._collaborations = {item for item in self._collaborations if item[1] != user_id}

    def clans(self) -> List[Dict[str, Any]]:
        rows = []
        for clan in self._clans.values():
            creator = self._users.get(clan.creator_id)
            rows.append(merge_dict(clan.__dict__, {
                "creator_user_id": creator.user_id if creator else "",
                "creator_name": creator.username if creator else "",
                "collaborators": len([item for item in self._collaborations if item[0] == clan.clan_id]),
            }))
        return rows

    def create_clan(self, payload: GenealogyIn) -> Dict[str, Any]:
        creator = next((user for user in self._users.values() if user.user_id == payload.creator_user_id), None)
        if not creator:
            raise HTTPException(status_code=404, detail="未找到创建者用户")
        clan_id = max(self._clans) + 1 if self._clans else 1
        clan = Genealogy(clan_id, payload.title, payload.surname or "", creator.id)
        self._clans[clan_id] = clan
        self._collaborations.add((clan_id, creator.id))
        return self.clans()[-1]

    def update_clan(self, clan_id: int, payload: GenealogyUpdate) -> Dict[str, Any]:
        clan = self._clans.get(clan_id)
        if not clan:
            raise HTTPException(status_code=404, detail="未找到族谱")
        changes = dump_model(payload, exclude_unset=True)
        if "title" in changes and changes["title"] is not None:
            clan.title = changes["title"]
        if "surname" in changes:
            clan.surname = changes["surname"] or ""
        clan.revised_at = datetime.now().isoformat(timespec="seconds")
        return next(row for row in self.clans() if row["clan_id"] == clan_id)

    def delete_clan(self, clan_id: int) -> None:
        if clan_id not in self._clans:
            raise HTTPException(status_code=404, detail="未找到族谱")
        member_ids = {member.member_id for member in self._members.values() if member.clan_id == clan_id}
        self._members = {mid: member for mid, member in self._members.items() if member.clan_id != clan_id}
        self._marriages = {pair for pair in self._marriages if pair[0] not in member_ids and pair[1] not in member_ids}
        self._collaborations = {item for item in self._collaborations if item[0] != clan_id}
        del self._clans[clan_id]

    def collaborators(self, clan_id: int) -> List[Dict[str, Any]]:
        if clan_id not in self._clans:
            raise HTTPException(status_code=404, detail="未找到族谱")
        rows = []
        for current_clan_id, user_id in sorted(self._collaborations):
            if current_clan_id != clan_id:
                continue
            user = self._users.get(user_id)
            if user:
                rows.append({"id": user.id, "user_id": user.user_id, "username": user.username})
        return rows

    def grant_collaboration(self, payload: CollaborationIn) -> Dict[str, Any]:
        user = next((item for item in self._users.values() if item.user_id == payload.user_id), None)
        if not user:
            raise HTTPException(status_code=404, detail="未找到用户")
        if payload.clan_id not in self._clans:
            raise HTTPException(status_code=404, detail="未找到族谱")
        self._collaborations.add((payload.clan_id, user.id))
        return {"ok": True, "message": f"已授权 {user.username or user.user_id} 编辑族谱"}

    def revoke_collaboration(self, payload: CollaborationIn) -> Dict[str, Any]:
        user = next((item for item in self._users.values() if item.user_id == payload.user_id), None)
        if not user:
            raise HTTPException(status_code=404, detail="未找到用户")
        clan = self._clans.get(payload.clan_id)
        if not clan:
            raise HTTPException(status_code=404, detail="未找到族谱")
        if clan.creator_id == user.id:
            raise HTTPException(status_code=400, detail="不能撤销创建者权限")
        self._collaborations.discard((payload.clan_id, user.id))
        return {"ok": True, "message": f"已撤销 {user.username or user.user_id} 的协作权限"}

    def dashboard(self, clan_id: Optional[int]) -> Dict[str, Any]:
        members = [
            m for m in self._members.values()
            if not clan_id or int(m.clan_id) == int(clan_id)
        ]
        male = sum(1 for m in members if m.gender == "M")
        female = sum(1 for m in members if m.gender == "F")
        unknown = sum(1 for m in members if m.gender == "U")
        oldest = min((m for m in members if m.birth_year), key=lambda m: m.birth_year, default=None)
        return {
            "clan_id": clan_id,
            "total_members": len(members),
            "gender": {"M": male, "F": female, "U": unknown},
            "oldest": public_member(oldest) if oldest else None,
            "collaborators": len([c for c in self._collaborations if not clan_id or c[0] == clan_id]),
        }

    def members(self, clan_id: int, q: str = "") -> List[Dict[str, Any]]:
        keyword = q.strip().lower()
        rows = [m for m in self._members.values() if not clan_id or m.clan_id == clan_id]
        if keyword:
            rows = [m for m in rows if keyword in m.name.lower() or keyword in str(m.member_id)]
        return [public_member(m) for m in sorted(rows, key=lambda item: (item.generation_num or 999, item.member_id))]

    def member_detail(self, member_id: int) -> Dict[str, Any]:
        member = self._find_member(member_id)
        clan = self._clans.get(member.clan_id)
        father = self._members.get(member.father_id) if member.father_id else None
        mother = self._members.get(member.mother_id) if member.mother_id else None
        children = [
            public_member(item)
            for item in self._members.values()
            if item.father_id == member_id or item.mother_id == member_id
        ]
        spouse_ids = set()
        for child in children:
            if child.get("father_id") == member_id and child.get("mother_id"):
                spouse_ids.add(child["mother_id"])
            if child.get("mother_id") == member_id and child.get("father_id"):
                spouse_ids.add(child["father_id"])
        for a_id, b_id in self._marriages:
            if a_id == member_id:
                spouse_ids.add(b_id)
            if b_id == member_id:
                spouse_ids.add(a_id)
        spouses = [public_member(self._members[sid]) for sid in sorted(spouse_ids) if sid in self._members]
        return {
            "member": public_member(member),
            "clan": clan.__dict__ if clan else None,
            "father": public_member(father) if father else None,
            "mother": public_member(mother) if mother else None,
            "spouses": spouses,
            "children": sorted(children, key=lambda item: int(item["member_id"])),
        }

    def create_member(self, payload: MemberIn) -> Dict[str, Any]:
        self._validate_gender(payload.gender)
        self._validate_years(payload.birth_year, payload.death_year)
        self._validate_demo_parent_links(payload.clan_id, None, payload.birth_year, payload.father_id, payload.mother_id)
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
        self._validate_demo_parent_links(
            member.clan_id,
            member_id,
            birth_year,
            changes.get("father_id", member.father_id),
            changes.get("mother_id", member.mother_id),
        )
        for key, value in changes.items():
            setattr(member, key, value)
        new_pair = self._parent_pair(member.father_id, member.mother_id)
        if old_pair != new_pair:
            self._cleanup_demo_marriage(old_pair)
            self._ensure_demo_marriage(member.father_id, member.mother_id)
        return public_member(member)

    def update_member_photo_hash(self, member_id: int, photo_hash: str, content: bytes = b"", content_type: str = "image/jpeg") -> Dict[str, Any]:
        member = self._find_member(member_id)
        member.id_pic = photo_hash
        if content:
            self._photo_blobs[photo_hash] = (content, content_type or "image/jpeg")
        return public_member(member)

    def member_photo(self, member_id: int) -> Optional[Tuple[bytes, str]]:
        member = self._find_member(member_id)
        if member.id_pic and member.id_pic in self._photo_blobs:
            return self._photo_blobs[member.id_pic]
        return None

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

    def member_marriages(self, member_id: int) -> List[Dict[str, Any]]:
        self._find_member(member_id)
        rows = []
        for index, (a_id, b_id) in enumerate(sorted(self._marriages), start=1):
            if member_id not in {a_id, b_id}:
                continue
            spouse_id = b_id if a_id == member_id else a_id
            spouse = self._members.get(spouse_id)
            if spouse:
                rows.append({
                    "marriage_id": index,
                    "clan_id": spouse.clan_id,
                    "spouse_id": spouse_id,
                    "spouse_name": spouse.name,
                    "marry_year": None,
                    "divorce_year": None,
                })
        return rows

    def create_marriage(self, payload: MarriageIn) -> Dict[str, Any]:
        member = self._find_member(payload.member_id)
        spouse_id = payload.spouse_id
        if not spouse_id and payload.spouse_name:
            matches = [item for item in self._members.values() if item.clan_id == member.clan_id and item.name == payload.spouse_name]
            if len(matches) != 1:
                raise HTTPException(status_code=400 if matches else 404, detail="配偶姓名不唯一或不存在，请使用成员 ID")
            spouse_id = matches[0].member_id
        if not spouse_id:
            raise HTTPException(status_code=400, detail="需要 spouse_id 或 spouse_name")
        spouse = self._find_member(spouse_id)
        if spouse.clan_id != member.clan_id:
            raise HTTPException(status_code=400, detail="配偶必须属于同一族谱")
        if spouse.member_id == member.member_id:
            raise HTTPException(status_code=400, detail="不能与自己建立婚姻")
        pair = tuple(sorted((member.member_id, spouse.member_id)))
        if pair in {tuple(sorted(item)) for item in self._marriages}:
            raise HTTPException(status_code=400, detail="两人已有婚姻记录")
        self._marriages.add((member.member_id, spouse.member_id))
        return {"ok": True, "message": "婚姻登记成功"}

    def set_divorce(self, marriage_id: int, payload: MarriageDivorceIn) -> Dict[str, Any]:
        if marriage_id < 1 or marriage_id > len(self._marriages):
            raise HTTPException(status_code=404, detail="婚姻记录不存在")
        return {"ok": True, "message": "demo 模式已记录离婚操作"}

    def delete_marriage(self, marriage_id: int) -> None:
        pairs = sorted(self._marriages)
        if marriage_id < 1 or marriage_id > len(pairs):
            raise HTTPException(status_code=404, detail="婚姻记录不存在")
        self._marriages.discard(pairs[marriage_id - 1])

    def invite(self, payload: InvitationIn) -> Dict[str, Any]:
        user = next((u for u in self._users.values() if u.user_id == payload.user_id), None)
        if not user:
            raise HTTPException(status_code=404, detail="未找到该用户")
        if payload.clan_id not in self._clans:
            raise HTTPException(status_code=404, detail="未找到该族谱")
        self._collaborations.add((payload.clan_id, user.id))
        return {"ok": True, "message": f"已邀请 {user.username} 编辑族谱"}

    def clan_permission(self, clan_id: int, user_id: str) -> Dict[str, bool]:
        user = next((item for item in self._users.values() if item.user_id == user_id), None)
        clan = self._clans.get(clan_id)
        is_owner = bool(user and clan and clan.creator_id == user.id)
        can_edit = bool(is_owner or (user and (clan_id, user.id) in self._collaborations))
        return {"can_edit": can_edit, "is_owner": is_owner}

    def _require_edit(self, clan_id: int, actor_user_id: Optional[str]) -> None:
        if actor_user_id and not self.clan_permission(clan_id, actor_user_id)["can_edit"]:
            raise HTTPException(status_code=403, detail="当前用户没有编辑该族谱的权限")

    def _require_owner(self, clan_id: int, actor_user_id: Optional[str]) -> None:
        if actor_user_id and not self.clan_permission(clan_id, actor_user_id)["is_owner"]:
            raise HTTPException(status_code=403, detail="只有族谱创建者可以执行该操作")

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

    def _validate_demo_parent_links(
        self,
        clan_id: int,
        member_id: Optional[int],
        birth_year: Optional[int],
        father_id: Optional[int],
        mother_id: Optional[int],
    ) -> None:
        for parent_id, role, required_gender in (
            (father_id, "父亲", "M"),
            (mother_id, "母亲", "F"),
        ):
            if not parent_id:
                continue
            if member_id and int(parent_id) == int(member_id):
                raise HTTPException(status_code=400, detail="不能把自己设为{}".format(role))
            parent = self._members.get(int(parent_id))
            if not parent:
                raise HTTPException(status_code=404, detail="{}不存在".format(role))
            if int(parent.clan_id) != int(clan_id):
                raise HTTPException(status_code=400, detail="{}必须属于同一族谱".format(role))
            if parent.gender != required_gender:
                raise HTTPException(status_code=400, detail="{}性别不符合要求".format(role))
            if birth_year and parent.birth_year and int(birth_year) <= int(parent.birth_year):
                raise HTTPException(status_code=400, detail="成员出生年份必须晚于{}出生年份".format(role))
            if birth_year and parent.death_year and int(birth_year) >= int(parent.death_year):
                raise HTTPException(status_code=400, detail="成员出生年份必须早于{}死亡年份".format(role))
        if father_id and mother_id and int(father_id) == int(mother_id):
            raise HTTPException(status_code=400, detail="父亲和母亲不能是同一个人")
        if member_id and birth_year:
            for child in self._members.values():
                if child.member_id != member_id and (child.father_id == member_id or child.mother_id == member_id):
                    if child.birth_year and int(birth_year) >= int(child.birth_year):
                        raise HTTPException(status_code=400, detail="成员出生年份必须早于子女出生年份")


class TotemGenealogyService(DemoGenealogyService):
    def __init__(self) -> None:
        super().__init__()
        self.client = TotemClient()

    def authenticate(self, user_id: str, password: str) -> Dict[str, Any]:
        try:
            rows = self.client.query(
                "SELECT id,user_id,username,password_hash,created_at FROM users "
                f"WHERE user_id = {sql_literal(user_id)} LIMIT 1;"
            )
            if not rows or not verify_password(password, rows[0].get("password_hash") or ""):
                raise HTTPException(status_code=401, detail="账号或密码不正确")
            if not is_password_hash(rows[0].get("password_hash") or ""):
                self.client.execute(
                    "UPDATE users SET password_hash = {} WHERE id = {};".format(
                        sql_literal(hash_password(password)),
                        sql_literal(int(rows[0]["id"])),
                    )
                )
            user = rows[0].copy()
            user.pop("password_hash", None)
            return {"ok": True, "user": user}
        except HTTPException:
            raise
        except Exception:
            return super().authenticate(user_id, password)

    def users(self) -> List[Dict[str, Any]]:
        try:
            return self.client.query("SELECT id,user_id,username,created_at FROM users ORDER BY id;")
        except Exception:
            return super().users()

    def user_detail(self, user_id: int) -> Dict[str, Any]:
        try:
            rows = self.client.query(
                "SELECT id,user_id,username,created_at FROM users "
                f"WHERE id = {sql_literal(user_id)} LIMIT 1;"
            )
            if not rows:
                raise HTTPException(status_code=404, detail="未找到用户")
            owned = self.client.query(
                "SELECT g.clan_id,g.title,g.surname,g.revised_at,g.creator_id,u.user_id AS creator_user_id,"
                "u.username AS creator_name,COALESCE(c.collaborators,0) AS collaborators "
                "FROM genealogies g "
                "LEFT JOIN users u ON u.id = g.creator_id "
                "LEFT JOIN (SELECT clan_id, COUNT(*) AS collaborators FROM collaborations GROUP BY clan_id) c "
                "ON c.clan_id = g.clan_id "
                f"WHERE g.creator_id = {sql_literal(user_id)} ORDER BY g.clan_id;"
            )
            collaborated = self.client.query(
                "SELECT g.clan_id,g.title,g.surname,g.revised_at,g.creator_id,u.user_id AS creator_user_id,"
                "u.username AS creator_name,COALESCE(cc.collaborators,0) AS collaborators "
                "FROM collaborations c "
                "JOIN genealogies g ON g.clan_id = c.clan_id "
                "LEFT JOIN users u ON u.id = g.creator_id "
                "LEFT JOIN (SELECT clan_id, COUNT(*) AS collaborators FROM collaborations GROUP BY clan_id) cc "
                "ON cc.clan_id = g.clan_id "
                f"WHERE c.user_id = {sql_literal(user_id)} AND g.creator_id <> {sql_literal(user_id)} "
                "ORDER BY g.clan_id;"
            )
            return {"user": rows[0], "owned_clans": owned, "collaborated_clans": collaborated}
        except HTTPException:
            raise
        except Exception:
            return super().user_detail(user_id)

    def create_user(self, payload: UserIn) -> Dict[str, Any]:
        try:
            exists = self.client.query(f"SELECT 1 FROM users WHERE user_id = {sql_literal(payload.user_id)} LIMIT 1;")
            if exists:
                raise HTTPException(status_code=409, detail="账号已存在")
            next_id_rows = self.client.query("SELECT COALESCE(MAX(id), 0) + 1 AS id FROM users;")
            user_id = int(next_id_rows[0]["id"]) if next_id_rows else 1
            self.client.execute(
                "INSERT INTO users(id,user_id,password_hash,username) "
                f"VALUES ({sql_literal(user_id)}, {sql_literal(payload.user_id)}, "
                f"{sql_literal(hash_password(payload.password))}, {sql_literal(payload.username or payload.user_id)});"
            )
            rows = self.client.query(
                "SELECT id,user_id,username,created_at FROM users "
                f"WHERE id = {sql_literal(user_id)} LIMIT 1;"
            )
            return rows[0]
        except HTTPException:
            raise
        except Exception:
            return super().create_user(payload)

    def update_user(self, user_id: int, payload: UserUpdate) -> Dict[str, Any]:
        try:
            changes = dump_model(payload, exclude_unset=True)
            if not changes:
                rows = self.client.query(
                    "SELECT id,user_id,username,created_at FROM users "
                    f"WHERE id = {sql_literal(user_id)} LIMIT 1;"
                )
                if not rows:
                    raise HTTPException(status_code=404, detail="未找到用户")
                return rows[0]
            assignments = []
            if "username" in changes:
                assignments.append(f"username = {sql_literal(changes['username'] or '')}")
            if changes.get("password"):
                assignments.append(f"password_hash = {sql_literal(hash_password(changes['password']))}")
            if assignments:
                self.client.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = {sql_literal(user_id)};")
            rows = self.client.query(
                "SELECT id,user_id,username,created_at FROM users "
                f"WHERE id = {sql_literal(user_id)} LIMIT 1;"
            )
            if not rows:
                raise HTTPException(status_code=404, detail="未找到用户")
            return rows[0]
        except HTTPException:
            raise
        except Exception:
            return super().update_user(user_id, payload)

    def delete_user(self, user_id: int) -> None:
        try:
            owned = self.client.query(
                f"SELECT 1 FROM genealogies WHERE creator_id = {sql_literal(user_id)} LIMIT 1;"
            )
            if owned:
                raise HTTPException(status_code=400, detail="该用户仍是族谱创建者，不能删除")
            self.client.execute(f"DELETE FROM collaborations WHERE user_id = {sql_literal(user_id)};")
            self.client.execute(f"DELETE FROM users WHERE id = {sql_literal(user_id)};")
        except HTTPException:
            raise
        except Exception:
            super().delete_user(user_id)

    def clans(self) -> List[Dict[str, Any]]:
        try:
            return self.client.query(
                "SELECT g.clan_id,g.title,g.surname,g.revised_at,g.creator_id,u.user_id AS creator_user_id,"
                "u.username AS creator_name,COALESCE(c.collaborators,0) AS collaborators "
                "FROM genealogies g LEFT JOIN users u ON u.id = g.creator_id "
                "LEFT JOIN (SELECT clan_id, COUNT(*) AS collaborators FROM collaborations GROUP BY clan_id) c "
                "ON c.clan_id = g.clan_id ORDER BY g.clan_id;"
            )
        except Exception:
            return super().clans()

    def create_clan(self, payload: GenealogyIn) -> Dict[str, Any]:
        try:
            creator_rows = self.client.query(
                f"SELECT id FROM users WHERE user_id = {sql_literal(payload.creator_user_id or 'admin')} LIMIT 1;"
            )
            if not creator_rows:
                raise HTTPException(status_code=404, detail="未找到创建者用户")
            creator_id = int(creator_rows[0]["id"])
            next_id_rows = self.client.query("SELECT COALESCE(MAX(clan_id), 0) + 1 AS clan_id FROM genealogies;")
            clan_id = int(next_id_rows[0]["clan_id"]) if next_id_rows else 1
            self.client.execute(
                "INSERT INTO genealogies(clan_id,title,surname,creator_id) "
                f"VALUES ({sql_literal(clan_id)}, {sql_literal(payload.title)}, "
                f"{sql_literal(payload.surname or '')}, {sql_literal(creator_id)});"
            )
            self.client.execute(
                "INSERT INTO collaborations(clan_id,user_id) "
                f"VALUES ({sql_literal(clan_id)}, {sql_literal(creator_id)});"
            )
            rows = [row for row in self.clans() if int(row["clan_id"]) == clan_id]
            return rows[0] if rows else {"clan_id": clan_id, "title": payload.title, "surname": payload.surname or ""}
        except HTTPException:
            raise
        except Exception:
            return super().create_clan(payload)

    def update_clan(self, clan_id: int, payload: GenealogyUpdate) -> Dict[str, Any]:
        try:
            changes = dump_model(payload, exclude_unset=True)
            if changes:
                assignments = []
                if "title" in changes and changes["title"] is not None:
                    assignments.append(f"title = {sql_literal(changes['title'])}")
                if "surname" in changes:
                    assignments.append(f"surname = {sql_literal(changes['surname'] or '')}")
                assignments.append("revised_at = CURRENT_TIMESTAMP")
                self.client.execute(
                    f"UPDATE genealogies SET {', '.join(assignments)} WHERE clan_id = {sql_literal(clan_id)};"
                )
            rows = [row for row in self.clans() if int(row["clan_id"]) == clan_id]
            if not rows:
                raise HTTPException(status_code=404, detail="未找到族谱")
            return rows[0]
        except HTTPException:
            raise
        except Exception:
            return super().update_clan(clan_id, payload)

    def delete_clan(self, clan_id: int) -> None:
        try:
            member_rows = self.client.query(
                f"SELECT member_id FROM members WHERE clan_id = {sql_literal(clan_id)};"
            )
            member_ids = [row["member_id"] for row in member_rows]
            if member_ids:
                id_list = ", ".join(sql_literal(int(member_id)) for member_id in member_ids)
                self.client.execute(f"DELETE FROM marriages WHERE clan_id = {sql_literal(clan_id)} OR spouse_a_id IN ({id_list}) OR spouse_b_id IN ({id_list});")
                self.client.execute(f"DELETE FROM members WHERE clan_id = {sql_literal(clan_id)};")
            else:
                self.client.execute(f"DELETE FROM marriages WHERE clan_id = {sql_literal(clan_id)};")
            self.client.execute(f"DELETE FROM collaborations WHERE clan_id = {sql_literal(clan_id)};")
            self.client.execute(f"DELETE FROM genealogies WHERE clan_id = {sql_literal(clan_id)};")
            self._sync_all_member_objects()
            self._sync_all_marriage_objects()
        except Exception:
            super().delete_clan(clan_id)

    def collaborators(self, clan_id: int) -> List[Dict[str, Any]]:
        try:
            return self.client.query(
                "SELECT u.id,u.user_id,u.username,u.created_at FROM collaborations c "
                "JOIN users u ON u.id = c.user_id "
                f"WHERE c.clan_id = {sql_literal(clan_id)} ORDER BY u.id;"
            )
        except Exception:
            return super().collaborators(clan_id)

    def grant_collaboration(self, payload: CollaborationIn) -> Dict[str, Any]:
        try:
            rows = self.client.query(f"SELECT id,username FROM users WHERE user_id = {sql_literal(payload.user_id)} LIMIT 1;")
            if not rows:
                raise HTTPException(status_code=404, detail="未找到用户")
            user_id = int(rows[0]["id"])
            exists = self.client.query(
                f"SELECT 1 FROM collaborations WHERE clan_id = {sql_literal(payload.clan_id)} AND user_id = {sql_literal(user_id)} LIMIT 1;"
            )
            if not exists:
                self.client.execute(
                    f"INSERT INTO collaborations(clan_id,user_id) VALUES ({sql_literal(payload.clan_id)}, {sql_literal(user_id)});"
                )
            return {"ok": True, "message": f"已授权 {rows[0].get('username') or payload.user_id} 编辑族谱"}
        except HTTPException:
            raise
        except Exception:
            return super().grant_collaboration(payload)

    def revoke_collaboration(self, payload: CollaborationIn) -> Dict[str, Any]:
        try:
            rows = self.client.query(f"SELECT id,username FROM users WHERE user_id = {sql_literal(payload.user_id)} LIMIT 1;")
            if not rows:
                raise HTTPException(status_code=404, detail="未找到用户")
            user_id = int(rows[0]["id"])
            owner = self.client.query(
                f"SELECT 1 FROM genealogies WHERE clan_id = {sql_literal(payload.clan_id)} AND creator_id = {sql_literal(user_id)} LIMIT 1;"
            )
            if owner:
                raise HTTPException(status_code=400, detail="不能撤销创建者权限")
            self.client.execute(
                f"DELETE FROM collaborations WHERE clan_id = {sql_literal(payload.clan_id)} AND user_id = {sql_literal(user_id)};"
            )
            return {"ok": True, "message": f"已撤销 {rows[0].get('username') or payload.user_id} 的协作权限"}
        except HTTPException:
            raise
        except Exception:
            return super().revoke_collaboration(payload)

    def clan_permission(self, clan_id: int, user_id: str) -> Dict[str, bool]:
        try:
            rows = self.client.query(
                "SELECT u.id FROM users u WHERE u.user_id = "
                f"{sql_literal(user_id)} LIMIT 1;"
            )
            if not rows:
                return {"can_edit": False, "is_owner": False}
            numeric_user_id = int(rows[0]["id"])
            owner = self.client.query(
                "SELECT 1 FROM genealogies WHERE "
                f"clan_id = {sql_literal(clan_id)} AND creator_id = {sql_literal(numeric_user_id)} LIMIT 1;"
            )
            is_owner = bool(owner)
            if is_owner:
                return {"can_edit": True, "is_owner": True}
            collab = self.client.query(
                "SELECT 1 FROM collaborations WHERE "
                f"clan_id = {sql_literal(clan_id)} AND user_id = {sql_literal(numeric_user_id)} LIMIT 1;"
            )
            return {"can_edit": bool(collab), "is_owner": False}
        except Exception:
            return super().clan_permission(clan_id, user_id)

    def dashboard(self, clan_id: Optional[int]) -> Dict[str, Any]:
        try:
            where = f"WHERE clan_id = {sql_literal(clan_id)}" if clan_id else ""
            total = self.client.query(f"SELECT COUNT(*) AS total FROM members {where};")
            gender = self.client.query(
                f"SELECT gender, COUNT(*) AS count FROM members {where} GROUP BY gender;"
            )
            oldest = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members {where + ' AND' if where else 'WHERE'} birth_year IS NOT NULL ORDER BY birth_year ASC LIMIT 1;"
            )
            counts = {"M": 0, "F": 0, "U": 0}
            for row in gender:
                counts[row.get("gender") or "U"] = int(row.get("count") or 0)
            return {
                "clan_id": clan_id,
                "total_members": int(total[0]["total"]) if total else 0,
                "gender": counts,
                "oldest": oldest[0] if oldest else None,
                "collaborators": len(self.collaborators(clan_id)) if clan_id else 0,
            }
        except Exception:
            return super().dashboard(clan_id)

    def members(self, clan_id: int, q: str = "") -> List[Dict[str, Any]]:
        try:
            where = []
            if clan_id:
                where.append(f"clan_id = {sql_literal(clan_id)}")
            if q.strip():
                where.append(f"name LIKE {sql_literal('%' + q.strip() + '%')}")
            where_sql = "WHERE " + " AND ".join(where) if where else ""
            sql = (
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members {where_sql} ORDER BY clan_id, generation_num, member_id LIMIT 200;"
            )
            return self.client.query(sql)
        except Exception:
            return super().members(clan_id, q)

    def member_detail(self, member_id: int) -> Dict[str, Any]:
        try:
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE member_id = {sql_literal(member_id)} LIMIT 1;"
            )
            if not rows:
                raise HTTPException(status_code=404, detail="未找到成员")
            member = rows[0]
            clan_id = self._optional_int(member.get("clan_id"))
            clan_rows = self.client.query(
                "SELECT g.clan_id,g.title,g.surname,g.revised_at,g.creator_id,u.user_id AS creator_user_id,u.username AS creator_name "
                "FROM genealogies g LEFT JOIN users u ON u.id = g.creator_id "
                f"WHERE g.clan_id = {sql_literal(clan_id)} LIMIT 1;"
            )
            relatives_by_id: Dict[int, Dict[str, Any]] = {}
            parent_ids = [
                self._optional_int(member.get("father_id")),
                self._optional_int(member.get("mother_id")),
            ]
            for parent_id in [item for item in parent_ids if item]:
                parent_rows = self.client.query(
                    "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                    f"FROM members WHERE member_id = {sql_literal(parent_id)} LIMIT 1;"
                )
                if parent_rows:
                    relatives_by_id[parent_id] = parent_rows[0]
            child_rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                "FROM members WHERE "
                f"father_id = {sql_literal(member_id)} OR mother_id = {sql_literal(member_id)} "
                "ORDER BY generation_num, member_id;"
            )
            spouse_rows = self.client.query(
                "SELECT DISTINCT s.member_id,s.clan_id,s.name,s.gender,s.birth_year,s.death_year,"
                "s.father_id,s.mother_id,s.generation_num,s.bio,s.id_pic "
                "FROM marriages ma JOIN members s ON "
                "((ma.spouse_a_id = s.member_id AND ma.spouse_b_id = {mid}) "
                "OR (ma.spouse_b_id = s.member_id AND ma.spouse_a_id = {mid})) "
                "WHERE ma.clan_id = {cid} "
                "ORDER BY s.member_id;".format(mid=sql_literal(member_id), cid=sql_literal(clan_id))
            )
            spouse_by_id = {int(row["member_id"]): row for row in spouse_rows}
            for child in child_rows:
                father_id = self._optional_int(child.get("father_id"))
                mother_id = self._optional_int(child.get("mother_id"))
                spouse_id = mother_id if father_id == member_id else father_id if mother_id == member_id else None
                if spouse_id and spouse_id not in spouse_by_id:
                    spouse_lookup = self.client.query(
                        "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                        f"FROM members WHERE member_id = {sql_literal(spouse_id)} LIMIT 1;"
                    )
                    if spouse_lookup:
                        spouse_by_id[spouse_id] = spouse_lookup[0]
            return {
                "member": member,
                "clan": clan_rows[0] if clan_rows else None,
                "father": relatives_by_id.get(self._optional_int(member.get("father_id")) or -1),
                "mother": relatives_by_id.get(self._optional_int(member.get("mother_id")) or -1),
                "spouses": list(spouse_by_id.values()),
                "children": child_rows,
            }
        except HTTPException:
            raise
        except Exception:
            return super().member_detail(member_id)

    def create_member(self, payload: MemberIn) -> Dict[str, Any]:
        try:
            self._validate_gender(payload.gender)
            self._validate_years(payload.birth_year, payload.death_year)
            next_id_rows = self.client.query("SELECT COALESCE(MAX(member_id), 0) + 1 AS member_id FROM members;")
            member_id = int(next_id_rows[0]["member_id"]) if next_id_rows else 1
            self._validate_parent_links(payload.clan_id, member_id, payload.birth_year, payload.father_id, payload.mother_id)
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
            self._sync_member_object(member_id)
            self._sync_all_marriage_objects()
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE member_id = {sql_literal(member_id)};"
            )
            return rows[0]
        except HTTPException:
            raise
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
            effective_clan_id = self._optional_int(before.get("clan_id")) or 1
            effective_birth_year = changes.get("birth_year")
            if effective_birth_year is None:
                current = self.client.query(
                    f"SELECT birth_year FROM members WHERE member_id = {sql_literal(member_id)} LIMIT 1;"
                )
                effective_birth_year = self._optional_int(current[0].get("birth_year")) if current else None
            self._validate_parent_links(
                effective_clan_id,
                member_id,
                effective_birth_year,
                changes.get("father_id", self._optional_int(before.get("father_id"))),
                changes.get("mother_id", self._optional_int(before.get("mother_id"))),
            )
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
                self._sync_all_marriage_objects()
            self._sync_member_object(member_id)
            return rows[0]
        except HTTPException:
            raise
        except Exception as exc:
            log_exception("error", exc, "update_member member_id={}".format(member_id))
            raise HTTPException(status_code=500, detail="更新成员失败：Totem 数据库执行异常，请查看 errorlog，成员 ID={}".format(member_id))

    def update_member_photo_hash(self, member_id: int, photo_hash: str, content: bytes = b"", content_type: str = "image/jpeg") -> Dict[str, Any]:
        try:
            self._ensure_photo_table()
            self._member_row(member_id, role="照片所属成员")
            if content:
                encoded = base64.b64encode(content).decode("ascii")
                exists = self.client.query(
                    f"SELECT 1 FROM member_photos WHERE photo_sha256 = {sql_literal(photo_hash)} LIMIT 1;"
                )
                if exists:
                    self.client.execute(
                        "UPDATE member_photos SET content_type = {ct}, content_base64 = {body}, updated_at = CURRENT_TIMESTAMP "
                        "WHERE photo_sha256 = {sha};".format(
                            ct=sql_literal(content_type or "image/jpeg"),
                            body=sql_literal(encoded),
                            sha=sql_literal(photo_hash),
                        )
                    )
                else:
                    self.client.execute(
                        "INSERT INTO member_photos(photo_sha256,content_type,content_base64) "
                        "VALUES ({},{},{});".format(
                            sql_literal(photo_hash),
                            sql_literal(content_type or "image/jpeg"),
                            sql_literal(encoded),
                        )
                    )
            self.client.execute(f"UPDATE members SET id_pic = {sql_literal(photo_hash)} WHERE member_id = {sql_literal(member_id)};")
            rows = self.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members WHERE member_id = {sql_literal(member_id)};"
            )
            if not rows:
                raise HTTPException(status_code=404, detail="未找到照片所属成员：ID {}".format(member_id))
            return rows[0]
        except HTTPException:
            raise
        except Exception as exc:
            log_exception("error", exc, "update_member_photo_hash member_id={}".format(member_id))
            raise HTTPException(status_code=500, detail="更新照片失败：Totem 数据库执行异常，请查看 errorlog，成员 ID={}".format(member_id))

    def member_photo(self, member_id: int) -> Optional[Tuple[bytes, str]]:
        try:
            self._ensure_photo_table()
            rows = self.client.query(
                "SELECT p.content_type,p.content_base64 FROM members m "
                "JOIN member_photos p ON p.photo_sha256 = m.id_pic "
                f"WHERE m.member_id = {sql_literal(member_id)} LIMIT 1;"
            )
            if not rows:
                return None
            content = base64.b64decode(rows[0].get("content_base64") or "")
            return content, rows[0].get("content_type") or "image/jpeg"
        except Exception:
            return super().member_photo(member_id)

    def delete_member(self, member_id: int) -> None:
        try:
            pairs = self._affected_parent_pairs_for_delete(member_id)
            self.client.execute(f"UPDATE members SET father_id = NULL WHERE father_id = {sql_literal(member_id)};")
            self.client.execute(f"UPDATE members SET mother_id = NULL WHERE mother_id = {sql_literal(member_id)};")
            self.client.execute(f"DELETE FROM members WHERE member_id = {sql_literal(member_id)};")
            for pair in pairs:
                self._cleanup_parent_marriage(pair)
            self._sync_all_member_objects()
            self._sync_all_marriage_objects()
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

    def member_marriages(self, member_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.client.query(
                "SELECT mg.marriage_id,mg.clan_id,mg.marry_year,mg.divorce_year,"
                "CASE WHEN mg.spouse_a_id = {mid} THEN mg.spouse_b_id ELSE mg.spouse_a_id END AS spouse_id,"
                "CASE WHEN mg.spouse_a_id = {mid} THEN mb.name ELSE ma.name END AS spouse_name "
                "FROM marriages mg JOIN members ma ON ma.member_id = mg.spouse_a_id "
                "JOIN members mb ON mb.member_id = mg.spouse_b_id "
                "WHERE mg.spouse_a_id = {mid} OR mg.spouse_b_id = {mid} "
                "ORDER BY mg.marry_year,mg.marriage_id;".format(mid=sql_literal(member_id))
            )
            return rows
        except Exception:
            return super().member_marriages(member_id)

    def create_marriage(self, payload: MarriageIn) -> Dict[str, Any]:
        try:
            member = self._member_row(payload.member_id)
            clan_id = self._optional_int(member.get("clan_id")) or 1
            spouse_id = payload.spouse_id
            if not spouse_id and payload.spouse_name:
                matches = self.client.query(
                    "SELECT member_id FROM members WHERE "
                    f"clan_id = {sql_literal(clan_id)} AND name = {sql_literal(payload.spouse_name)};"
                )
                if not matches:
                    raise HTTPException(status_code=404, detail="同族谱中未找到配偶")
                if len(matches) > 1:
                    raise HTTPException(status_code=400, detail="配偶姓名对应多个成员，请使用成员 ID")
                spouse_id = self._optional_int(matches[0].get("member_id"))
            if not spouse_id:
                raise HTTPException(status_code=400, detail="需要 spouse_id 或 spouse_name")
            spouse = self._member_row(int(spouse_id))
            if self._optional_int(spouse.get("clan_id")) != clan_id:
                raise HTTPException(status_code=400, detail="配偶必须属于同一族谱")
            if int(spouse_id) == int(payload.member_id):
                raise HTTPException(status_code=400, detail="不能与自己建立婚姻")
            if payload.marry_year and payload.divorce_year and payload.divorce_year <= payload.marry_year:
                raise HTTPException(status_code=400, detail="离婚年份必须晚于结婚年份")
            self._validate_marriage_years(payload.member_id, int(spouse_id), payload.marry_year, payload.divorce_year)
            self._ensure_no_marriage_overlap(payload.member_id, payload.marry_year, payload.divorce_year)
            self._ensure_no_marriage_overlap(int(spouse_id), payload.marry_year, payload.divorce_year)
            existing = self.client.query(
                "SELECT 1 FROM marriages WHERE clan_id = {cid} AND "
                "((spouse_a_id = {a} AND spouse_b_id = {b}) OR (spouse_a_id = {b} AND spouse_b_id = {a})) "
                "AND divorce_year IS NULL LIMIT 1;".format(
                    cid=sql_literal(clan_id),
                    a=sql_literal(payload.member_id),
                    b=sql_literal(int(spouse_id)),
                )
            )
            if existing:
                raise HTTPException(status_code=400, detail="两人已有有效婚姻记录")
            next_id_rows = self.client.query("SELECT COALESCE(MAX(marriage_id), 0) + 1 AS marriage_id FROM marriages;")
            marriage_id = int(next_id_rows[0]["marriage_id"]) if next_id_rows else 1
            self.client.execute(
                "INSERT INTO marriages(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year) "
                "VALUES ({},{},{},{},{},{});".format(
                    sql_literal(marriage_id),
                    sql_literal(clan_id),
                    sql_literal(payload.member_id),
                    sql_literal(int(spouse_id)),
                    sql_literal(payload.marry_year),
                    sql_literal(payload.divorce_year),
                )
            )
            self._sync_marriage_object(marriage_id)
            return {"ok": True, "marriage_id": marriage_id, "message": "婚姻登记成功"}
        except HTTPException:
            raise
        except Exception:
            return super().create_marriage(payload)

    def set_divorce(self, marriage_id: int, payload: MarriageDivorceIn) -> Dict[str, Any]:
        try:
            row = self._marriage_row(marriage_id)
            marry_year = self._optional_int(row.get("marry_year"))
            if marry_year and payload.divorce_year and payload.divorce_year <= marry_year:
                raise HTTPException(status_code=400, detail="离婚年份必须晚于结婚年份")
            self.client.execute(
                f"UPDATE marriages SET divorce_year = {sql_literal(payload.divorce_year)} "
                f"WHERE marriage_id = {sql_literal(marriage_id)};"
            )
            self._sync_marriage_object(marriage_id)
            return {"ok": True, "message": "离婚信息已更新"}
        except HTTPException:
            raise
        except Exception:
            return super().set_divorce(marriage_id, payload)

    def delete_marriage(self, marriage_id: int) -> None:
        try:
            self._marriage_row(marriage_id)
            self.client.execute(f"DELETE FROM marriages WHERE marriage_id = {sql_literal(marriage_id)};")
            self._delete_marriage_object(marriage_id)
        except HTTPException:
            raise
        except Exception:
            super().delete_marriage(marriage_id)

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

    def _sync_member_object(self, member_id: int) -> None:
        try:
            self.client.execute(f"DELETE FROM member_objects WHERE member_id = {sql_literal(member_id)};")
            self.client.execute(
                "INSERT INTO member_objects(member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num) "
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num "
                f"FROM members WHERE member_id = {sql_literal(member_id)};"
            )
        except Exception as exc:
            log_exception("error", exc, "sync_member_object member_id={}".format(member_id))

    def _sync_marriage_object(self, marriage_id: int) -> None:
        try:
            self.client.execute(f"DELETE FROM marriage_objects WHERE marriage_id = {sql_literal(marriage_id)};")
            self.client.execute(
                "INSERT INTO marriage_objects(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year) "
                "SELECT marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year "
                f"FROM marriages WHERE marriage_id = {sql_literal(marriage_id)};"
            )
        except Exception as exc:
            log_exception("error", exc, "sync_marriage_object marriage_id={}".format(marriage_id))

    def _delete_marriage_object(self, marriage_id: int) -> None:
        try:
            self.client.execute(f"DELETE FROM marriage_objects WHERE marriage_id = {sql_literal(marriage_id)};")
        except Exception as exc:
            log_exception("error", exc, "delete_marriage_object marriage_id={}".format(marriage_id))

    def _sync_all_member_objects(self) -> None:
        try:
            self.client.execute("DELETE FROM member_objects;")
            self.client.execute(
                "INSERT INTO member_objects(member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num) "
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num "
                "FROM members;"
            )
        except Exception as exc:
            log_exception("error", exc, "sync_all_member_objects")

    def _sync_all_marriage_objects(self) -> None:
        try:
            self.client.execute("DELETE FROM marriage_objects;")
            self.client.execute(
                "INSERT INTO marriage_objects(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year) "
                "SELECT marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year "
                "FROM marriages;"
            )
        except Exception as exc:
            log_exception("error", exc, "sync_all_marriage_objects")

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value in {None, "", "NULL"}:
            return None
        return int(value)

    def _member_row(self, member_id: int, role: str = "成员") -> Dict[str, Any]:
        rows = self.client.query(
            "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
            f"FROM members WHERE member_id = {sql_literal(member_id)} LIMIT 1;"
        )
        if not rows:
            raise HTTPException(status_code=404, detail="未找到{}：ID {}".format(role, member_id))
        return rows[0]

    def _ensure_photo_table(self) -> None:
        try:
            self.client.query("SELECT photo_sha256 FROM member_photos LIMIT 1;")
            return
        except Exception:
            pass
        self.client.execute(
            "CREATE TABLE member_photos ("
            "photo_sha256 VARCHAR(64) PRIMARY KEY,"
            "content_type VARCHAR(100) NOT NULL,"
            "content_base64 TEXT NOT NULL,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ");"
        )

    def _marriage_row(self, marriage_id: int) -> Dict[str, Any]:
        rows = self.client.query(
            "SELECT marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year "
            f"FROM marriages WHERE marriage_id = {sql_literal(marriage_id)} LIMIT 1;"
        )
        if not rows:
            raise HTTPException(status_code=404, detail="婚姻记录不存在")
        return rows[0]

    def _validate_parent_links(
        self,
        clan_id: int,
        member_id: Optional[int],
        birth_year: Optional[int],
        father_id: Optional[int],
        mother_id: Optional[int],
    ) -> None:
        if father_id and mother_id and int(father_id) == int(mother_id):
            raise HTTPException(status_code=400, detail="父亲和母亲不能是同一个人")
        for parent_id, role, required_gender in (
            (father_id, "父亲", "M"),
            (mother_id, "母亲", "F"),
        ):
            if not parent_id:
                continue
            if member_id and int(parent_id) == int(member_id):
                raise HTTPException(status_code=400, detail="不能把自己设为{}".format(role))
            parent = self._member_row(int(parent_id), role=role)
            if self._optional_int(parent.get("clan_id")) != int(clan_id):
                raise HTTPException(status_code=400, detail="{}必须属于同一族谱".format(role))
            if parent.get("gender") != required_gender:
                raise HTTPException(status_code=400, detail="{}性别必须为{}".format(role, "男" if required_gender == "M" else "女"))
            parent_birth = self._optional_int(parent.get("birth_year"))
            parent_death = self._optional_int(parent.get("death_year"))
            if birth_year and parent_birth and int(birth_year) <= parent_birth:
                raise HTTPException(status_code=400, detail="成员出生年份必须晚于{}出生年份".format(role))
            if birth_year and parent_death and int(birth_year) >= parent_death:
                raise HTTPException(status_code=400, detail="成员出生年份必须早于{}死亡年份".format(role))
        if member_id and birth_year:
            children = self.client.query(
                "SELECT birth_year FROM members WHERE "
                f"(father_id = {sql_literal(member_id)} OR mother_id = {sql_literal(member_id)}) "
                "AND birth_year IS NOT NULL;"
            )
            for child in children:
                child_birth = self._optional_int(child.get("birth_year"))
                if child_birth and int(birth_year) >= child_birth:
                    raise HTTPException(status_code=400, detail="成员出生年份必须早于子女出生年份")

    def _interval_end(self, year: Optional[int]) -> int:
        return int(year) if year else 9999

    def _validate_marriage_years(self, member_id: int, spouse_id: int, marry_year: Optional[int], divorce_year: Optional[int]) -> None:
        for current_id, role in ((member_id, "成员"), (spouse_id, "配偶")):
            row = self._member_row(current_id)
            birth = self._optional_int(row.get("birth_year"))
            death = self._optional_int(row.get("death_year"))
            if marry_year and birth and marry_year <= birth:
                raise HTTPException(status_code=400, detail="结婚年份必须晚于{}出生年份".format(role))
            if marry_year and death and marry_year >= death:
                raise HTTPException(status_code=400, detail="结婚年份必须早于{}死亡年份".format(role))
            if divorce_year and death and divorce_year >= death:
                raise HTTPException(status_code=400, detail="离婚年份必须早于{}死亡年份".format(role))

    def _ensure_no_marriage_overlap(
        self,
        member_id: int,
        start_year: Optional[int],
        end_year: Optional[int],
        ignore_marriage_id: Optional[int] = None,
    ) -> None:
        if not start_year:
            start_year = 0
        rows = self.client.query(
            "SELECT marriage_id,marry_year,divorce_year FROM marriages WHERE "
            f"(spouse_a_id = {sql_literal(member_id)} OR spouse_b_id = {sql_literal(member_id)});"
        )
        for row in rows:
            current_marriage_id = self._optional_int(row.get("marriage_id"))
            if ignore_marriage_id and current_marriage_id == ignore_marriage_id:
                continue
            old_start = self._optional_int(row.get("marry_year")) or 0
            old_end = self._optional_int(row.get("divorce_year"))
            if start_year < self._interval_end(old_end) and self._interval_end(end_year) > old_start:
                raise HTTPException(status_code=400, detail="该成员在该时间段已有婚姻关系")

    def _member_parent_row(self, member_id: int) -> Dict[str, Any]:
        rows = self.client.query(
            "SELECT member_id,clan_id,father_id,mother_id FROM members "
            f"WHERE member_id = {sql_literal(member_id)} LIMIT 1;"
        )
        if not rows:
            raise HTTPException(status_code=404, detail="未找到要编辑的成员：ID {}".format(member_id))
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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    log_error(
        "error",
        "{} {} status={} detail={}".format(
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        ),
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    log_error(
        "error",
        "{} {} validation={}".format(request.method, request.url.path, exc.errors()),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    log_exception("crash", exc, "{} {} error_id={}".format(request.method, request.url.path, error_id))
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请查看 log/errorlog.txt，错误编号：{}".format(error_id), "error_id": error_id},
    )


def load_script_module(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, APP_DIR / filename)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail="无法加载脚本 {}".format(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def import_tools():
    return load_script_module("import.py", "genealogy_import_tools")


def export_tools():
    return load_script_module("export.py", "genealogy_export_tools")


def ensure_output_dir(*parts: str) -> Path:
    output_dir = APP_DIR / "output"
    for part in parts:
        output_dir = output_dir / part
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


for output_part in ("import", "export", "performance-test"):
    ensure_output_dir(output_part)


def require_actor(current_user_id: Optional[str]) -> str:
    if not current_user_id:
        raise HTTPException(status_code=401, detail="缺少当前登录用户")
    return current_user_id


def require_admin(current_user_id: Optional[str]) -> str:
    actor = require_actor(current_user_id)
    if actor != "admin":
        raise HTTPException(status_code=403, detail="只有 admin 可以管理用户")
    return actor


def record_action(current_user_id: Optional[str], log_session: Optional[str], action_type: str, target: Any) -> None:
    if current_user_id:
        log_user_action(current_user_id, log_session or "", action_type, target)


def require_clan_edit(clan_id: int, current_user_id: Optional[str]) -> None:
    actor = require_actor(current_user_id)
    if not service.clan_permission(clan_id, actor)["can_edit"]:
        raise HTTPException(status_code=403, detail="当前用户没有编辑该族谱的权限")


def require_clan_owner(clan_id: int, current_user_id: Optional[str]) -> None:
    actor = require_actor(current_user_id)
    if not service.clan_permission(clan_id, actor)["is_owner"]:
        raise HTTPException(status_code=403, detail="只有族谱创建者可以执行该操作")


def member_clan_id(member_id: int) -> int:
    detail = service.member_detail(member_id)
    return int(detail["member"]["clan_id"])


def marriage_clan_id(marriage_id: int) -> int:
    for row in all_marriages_for_member(0):
        if int(row["marriage_id"]) == int(marriage_id):
            return int(row["clan_id"])
    if hasattr(service, "client"):
        rows = service.client.query(  # type: ignore[attr-defined]
            f"SELECT clan_id FROM marriages WHERE marriage_id = {sql_literal(marriage_id)} LIMIT 1;"
        )
        if rows:
            return int(rows[0]["clan_id"])
    if not hasattr(service, "client"):
        return 1
    raise HTTPException(status_code=404, detail="婚姻记录不存在")


def all_marriages_for_member(member_id: int) -> List[Dict[str, Any]]:
    if hasattr(service, "member_marriages"):
        try:
            return service.member_marriages(member_id)
        except Exception:
            return []
    return []


def all_member_rows(clan_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if hasattr(service, "client"):
        try:
            where = f"WHERE clan_id = {sql_literal(clan_id)}" if clan_id else ""
            return service.client.query(
                "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
                f"FROM members {where} ORDER BY clan_id,generation_num,member_id;"
            )
        except Exception:
            if not hasattr(service, "_members"):
                raise
    rows = []
    for member in service._members.values():  # type: ignore[attr-defined]
        if clan_id and int(member.clan_id) != int(clan_id):
            continue
        rows.append(public_member(member))
    return sorted(rows, key=lambda item: (int(item["clan_id"]), int(item.get("generation_num") or 999), int(item["member_id"])))


def query_deputy_class(class_name: str, sql: str) -> Optional[List[Dict[str, Any]]]:
    if not hasattr(service, "client"):
        return None
    try:
        service.client.query("SELECT 1 FROM {} LIMIT 1;".format(class_name))  # type: ignore[attr-defined]
        return service.client.query(sql)  # type: ignore[attr-defined]
    except Exception:
        return None


def deputy_member_details(member_ids: List[int]) -> Optional[List[Dict[str, Any]]]:
    if not member_ids or not hasattr(service, "client"):
        return [] if not member_ids else None
    id_list = ",".join(str(int(item)) for item in sorted(set(member_ids)))
    try:
        rows = service.client.query(  # type: ignore[attr-defined]
            "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
            "FROM members WHERE member_id IN ({}) ORDER BY member_id;".format(id_list)
        )
        by_id = {int(row["member_id"]): row for row in rows}
        return [by_id[item] for item in member_ids if item in by_id]
    except Exception:
        return None


def deputy_parent_edges(member_id: int) -> Optional[List[Dict[str, Any]]]:
    father = query_deputy_class(
        "father_up_edges",
        "SELECT from_member_id,to_member_id,'father' AS parent_role FROM father_up_edges "
        "WHERE from_member_id = {};".format(sql_literal(member_id)),
    )
    mother = query_deputy_class(
        "mother_up_edges",
        "SELECT from_member_id,to_member_id,'mother' AS parent_role FROM mother_up_edges "
        "WHERE from_member_id = {};".format(sql_literal(member_id)),
    )
    if father is None or mother is None:
        return None
    return father + mother


def deputy_child_edges(member_id: int) -> Optional[List[Dict[str, Any]]]:
    father = query_deputy_class(
        "father_down_edges",
        "SELECT from_member_id,to_member_id,'father' AS parent_role FROM father_down_edges "
        "WHERE from_member_id = {};".format(sql_literal(member_id)),
    )
    mother = query_deputy_class(
        "mother_down_edges",
        "SELECT from_member_id,to_member_id,'mother' AS parent_role FROM mother_down_edges "
        "WHERE from_member_id = {};".format(sql_literal(member_id)),
    )
    if father is None or mother is None:
        return None
    return father + mother


def deputy_ancestor_rows(member_id: int) -> Optional[List[Dict[str, Any]]]:
    if query_deputy_class("father_up_edges", "SELECT 1 FROM father_up_edges LIMIT 1;") is None:
        return None
    result_ids: List[Tuple[int, int]] = []
    queue: Deque[Tuple[int, int]] = deque([(member_id, 0)])
    seen: Set[int] = {member_id}
    while queue:
        current_id, depth = queue.popleft()
        edges = deputy_parent_edges(current_id)
        if edges is None:
            return None
        for edge in edges:
            parent_id = optional_row_int(edge, "to_member_id")
            if parent_id and parent_id not in seen:
                seen.add(parent_id)
                result_ids.append((parent_id, depth + 1))
                queue.append((parent_id, depth + 1))
    details = deputy_member_details([item[0] for item in result_ids])
    if details is None:
        return None
    depth_by_id = {member_id: depth for member_id, depth in result_ids}
    return [merge_dict(row, {"generations_above": depth_by_id[int(row["member_id"])]}) for row in details]


def deputy_great_grandchildren_rows(member_id: int) -> Optional[List[Dict[str, Any]]]:
    generation_ids = [member_id]
    for _ in range(3):
        next_ids: List[int] = []
        for current_id in generation_ids:
            edges = deputy_child_edges(current_id)
            if edges is None:
                return None
            next_ids.extend([optional_row_int(edge, "to_member_id") for edge in edges if optional_row_int(edge, "to_member_id")])
        generation_ids = sorted(set(int(item) for item in next_ids))
    details = deputy_member_details(generation_ids)
    return sorted(details, key=lambda item: int(item["member_id"]))[:300] if details is not None else None


def deputy_relationship_path(source_id: int, target_id: int) -> Optional[List[Dict[str, Any]]]:
    if query_deputy_class("father_down_edges", "SELECT 1 FROM father_down_edges LIMIT 1;") is None:
        return None
    edge_queries = [
        ("father_down_edges", "SELECT from_member_id,to_member_id FROM father_down_edges"),
        ("mother_down_edges", "SELECT from_member_id,to_member_id FROM mother_down_edges"),
        ("spouse_a_edges", "SELECT from_member_id,to_member_id FROM spouse_a_edges"),
        ("spouse_b_edges", "SELECT from_member_id,to_member_id FROM spouse_b_edges"),
    ]
    graph: Dict[int, Set[int]] = {}
    for class_name, sql in edge_queries:
        rows = query_deputy_class(class_name, sql + ";")
        if rows is None:
            return None
        for row in rows:
            a = optional_row_int(row, "from_member_id")
            b = optional_row_int(row, "to_member_id")
            if a and b:
                graph.setdefault(a, set()).add(b)
                graph.setdefault(b, set()).add(a)
    if source_id not in graph or target_id not in graph:
        return []
    queue: Deque[List[int]] = deque([[source_id]])
    seen = {source_id}
    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == target_id:
            details = deputy_member_details(path)
            return details if details is not None else None
        for next_id in sorted(graph.get(current, set())):
            if next_id not in seen:
                seen.add(next_id)
                queue.append(path + [next_id])
    return []


def member_rows_by_name(name: str) -> List[Dict[str, Any]]:
    return [row for row in all_member_rows() if row.get("name") == name]


def resolve_query_member_id(member_id: Optional[int], name: Optional[str]) -> int:
    if member_id is not None:
        detail = service.member_detail(member_id)
        if name and (detail.get("member") or {}).get("name") != name.strip():
            actual_name = (detail.get("member") or {}).get("name") or "-"
            raise HTTPException(status_code=400, detail=f"确认 ID 对应姓名为 {actual_name}，不是 {name}")
        return int(member_id)
    if not name:
        raise HTTPException(status_code=400, detail="需要 member_id 或 name")
    matches = member_rows_by_name(name.strip())
    if not matches:
        raise HTTPException(status_code=404, detail=f"未找到成员：{name}")
    if len(matches) > 1:
        choices = "；".join(
            "{} #{}（族谱 {}，第{}代）".format(
                row.get("name"),
                row.get("member_id"),
                row.get("clan_id"),
                row.get("generation_num") or "-",
            )
            for row in matches[:10]
        )
        raise HTTPException(status_code=409, detail=f"成员存在重名，请填写具体 ID：{choices}")
    return int(matches[0]["member_id"])


def optional_row_int(row: Dict[str, Any], key: str) -> Optional[int]:
    value = row.get(key)
    if value in {None, "", "NULL"}:
        return None
    return int(value)


def row_age(row: Dict[str, Any]) -> Optional[int]:
    birth_year = optional_row_int(row, "birth_year")
    if not birth_year:
        return None
    death_year = optional_row_int(row, "death_year") or datetime.now().year
    return death_year - birth_year


def configure_member_indexes(performance_mode: bool) -> Dict[str, Any]:
    mode = "performance" if performance_mode else "normal"
    result = {"mode": mode, "enabled": performance_mode, "indexes": [], "errors": []}
    if not hasattr(service, "client"):
        result["message"] = "demo 模式不操作真实数据库索引"
        return result

    client = service.client  # type: ignore[attr-defined]
    if performance_mode:
        for index_name, create_sql in MEMBER_PERFORMANCE_INDEXES:
            try:
                client.execute(create_sql + ";")
                result["indexes"].append(index_name)
            except Exception as exc:
                message = str(exc)
                if "already exists" in message or "已存在" in message:
                    result["indexes"].append(index_name)
                else:
                    result["errors"].append(f"{index_name}: {message}")
    else:
        for index_name, _ in reversed(MEMBER_INDEXES_TO_DROP):
            try:
                client.execute(f"DROP INDEX {index_name};")
            except Exception as exc:
                message = str(exc)
                if "does not exist" not in message and "不存在" not in message:
                    result["errors"].append(f"{index_name}: {message}")
    return result


def member_search_sql(clan_id: int, q: str, performance_mode: bool) -> str:
    keyword = q.strip()
    select_sql = (
        "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
        "FROM members"
    )
    scope = []
    if clan_id:
        scope.append("clan_id = {}".format(sql_literal(clan_id)))

    if performance_mode:
        conditions = []
        if keyword.isdigit():
            conditions.append("member_id = {}".format(sql_literal(int(keyword))))
        upper = prefix_upper_bound(keyword)
        if upper:
            conditions.append("(name >= {} AND name < {})".format(sql_literal(keyword), sql_literal(upper)))
        else:
            conditions.append("name = {}".format(sql_literal(keyword)))
        where_parts = scope + ["(" + " OR ".join(conditions) + ")"]
    else:
        conditions = [
            "name LIKE {}".format(sql_literal("%" + keyword + "%")),
            "CAST(member_id AS TEXT) LIKE {}".format(sql_literal("%" + keyword + "%")),
        ]
        where_parts = scope + ["(" + " OR ".join(conditions) + ")"]

    where_sql = " WHERE " + " AND ".join(where_parts) if where_parts else ""
    order_sql = " LIMIT 200" if performance_mode else " ORDER BY clan_id,generation_num,member_id LIMIT 200"
    return select_sql + where_sql + order_sql


def prefix_upper_bound(value: str) -> str:
    if not value:
        return ""
    codepoints = [ord(ch) for ch in value]
    codepoints[-1] += 1
    return "".join(chr(item) for item in codepoints)


def indexed_member_search(clan_id: int, q: str, performance_mode: bool) -> List[Dict[str, Any]]:
    if hasattr(service, "client"):
        return service.client.query(member_search_sql(clan_id, q, performance_mode) + ";")  # type: ignore[attr-defined]
    keyword = q.strip().lower()
    rows = all_member_rows(clan_id or None)
    if performance_mode:
        matched = []
        for row in rows:
            name = str(row.get("name", ""))
            member_id = str(row.get("member_id", ""))
            if member_id == q.strip() or name == q.strip() or name.startswith(q.strip()):
                matched.append(row)
        return matched[:200]
    return [
        row for row in rows
        if keyword in str(row.get("name", "")).lower()
        or keyword in str(row.get("member_id", ""))
    ][:200]


def measured_member_search(clan_id: int, q: str, performance_mode: bool) -> Dict[str, Any]:
    keyword = q.strip().lower()
    if not keyword:
        mode = "performance" if performance_mode else "normal"
        return {
            "ok": False,
            "mode": mode,
            "index_status": {
                "mode": mode,
                "enabled": performance_mode,
                "indexes": [],
                "errors": [],
                "message": "空查询未执行",
            },
            "elapsed_ms": 0,
            "memory_kb": 0,
            "count": 0,
            "rows": [],
            "error": "请输入姓名或编号后查询",
        }
    index_status = configure_member_indexes(performance_mode)
    tracemalloc.start()
    started = time.perf_counter()
    try:
        rows = indexed_member_search(clan_id, q, performance_mode)
        elapsed_ms = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        return {
            "ok": True,
            "mode": index_status["mode"],
            "index_status": index_status,
            "elapsed_ms": round(elapsed_ms, 3),
            "memory_kb": round(peak / 1024, 2),
            "count": len(rows),
            "rows": rows,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        _, peak = tracemalloc.get_traced_memory()
        return {
            "ok": False,
            "mode": index_status["mode"],
            "index_status": index_status,
            "elapsed_ms": round(elapsed_ms, 3),
            "memory_kb": round(peak / 1024, 2),
            "count": 0,
            "rows": [],
            "error": str(exc),
        }
    finally:
        tracemalloc.stop()


def run_tsql_text(args: List[str], timeout: int = 120) -> str:
    command = [TSQL_BIN]
    if TOTEM_PORT:
        command.extend(["-p", TOTEM_PORT])
    if TOTEM_USER:
        command.extend(["-U", TOTEM_USER])
    command.extend(["-d", DATABASE_NAME])
    command.extend(args)
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout


def write_search_explain(q: str, clan_id: int = 0, performance_mode: bool = False) -> Dict[str, Any]:
    keyword = q.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="请输入搜索关键词")
    index_status = configure_member_indexes(performance_mode)
    sql = member_search_sql(clan_id, keyword, performance_mode)
    explain_sql = "EXPLAIN ANALYZE " + sql + ";"
    output = run_tsql_text(["-c", explain_sql], timeout=180)
    target_dir = ensure_output_dir("performance-test")
    file_path = target_dir / (datetime.now().strftime("%Y%m%d-%H%M%S") + ".txt")
    content = "\n".join([
        "Totem genealogy performance EXPLAIN",
        "generated_at: {}".format(datetime.now().isoformat(timespec="seconds")),
        "mode: {}".format(index_status.get("mode")),
        "index_status: {}".format(index_status),
        "keyword: {}".format(keyword),
        "clan_id: {}".format(clan_id or "all"),
        "",
        "SQL:",
        sql + ";",
        "",
        "EXPLAIN ANALYZE:",
        output,
    ])
    file_path.write_text(content, encoding="utf-8")
    return {"ok": True, "output_file": str(file_path), "mode": index_status.get("mode"), "index_status": index_status}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(
        render_app(),
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.post("/api/login")
def login(payload: LoginRequest) -> Dict[str, Any]:
    result = service.authenticate(payload.user_id, payload.password)
    session = start_user_log(payload.user_id)
    result["log_session"] = session
    record_action(payload.user_id, session, "log-in", payload.user_id)
    return result


@app.post("/api/logout")
def logout(current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    record_action(actor, log_session, "log-out", actor)
    return {"ok": True}


@app.post("/api/register", status_code=201)
def register(payload: UserIn) -> Dict[str, Any]:
    """Public self-registration endpoint. Anyone can create a non-admin account."""
    if payload.user_id.lower() == "admin":
        raise HTTPException(status_code=400, detail="admin 账号不能通过公开注册创建")
    return service.create_user(payload)


@app.get("/api/users")
def list_users(current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> List[Dict[str, Any]]:
    actor = require_admin(current_user_id)
    record_action(actor, log_session, "search-user", "all")
    return service.users()


@app.get("/api/users/{user_id}/detail")
def user_detail(user_id: int, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_admin(current_user_id)
    record_action(actor, log_session, "search-user", user_id)
    return service.user_detail(user_id)


@app.post("/api/users", status_code=201)
def create_user(payload: UserIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_admin(current_user_id)
    result = service.create_user(payload)
    record_action(actor, log_session, "add-user", result.get("user_id", payload.user_id))
    return result


@app.put("/api/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    require_admin(current_user_id)
    return service.update_user(user_id, payload)


@app.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: int, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> None:
    actor = require_admin(current_user_id)
    service.delete_user(user_id)
    record_action(actor, log_session, "remove-user", user_id)


@app.get("/api/clans")
def list_clans() -> List[Dict[str, Any]]:
    return service.clans()


@app.post("/api/clans", status_code=201)
def create_clan(payload: GenealogyIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    payload.creator_user_id = actor
    result = service.create_clan(payload)
    record_action(actor, log_session, "add-data", "clan:{}".format(result.get("clan_id", "")))
    return result


@app.put("/api/clans/{clan_id}")
def update_clan(clan_id: int, payload: GenealogyUpdate, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_owner(clan_id, actor)
    result = service.update_clan(clan_id, payload)
    record_action(actor, log_session, "add-data", "clan:{}".format(clan_id))
    return result


@app.delete("/api/clans/{clan_id}", status_code=204)
def delete_clan(clan_id: int, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> None:
    actor = require_actor(current_user_id)
    require_clan_owner(clan_id, actor)
    service.delete_clan(clan_id)
    record_action(actor, log_session, "remove-data", "clan:{}".format(clan_id))


@app.get("/api/clans/{clan_id}/collaborators")
def list_collaborators(clan_id: int) -> List[Dict[str, Any]]:
    return service.collaborators(clan_id)


@app.get("/api/clans/{clan_id}/permission")
def clan_permission(clan_id: int, current_user_id: str = Query(..., min_length=1)) -> Dict[str, bool]:
    return service.clan_permission(clan_id, current_user_id)


@app.post("/api/import/clan-csv")
async def import_clan_from_csv(
    csv_file: UploadFile = File(...),
    title: str = Form(...),
    surname: str = Form(""),
    current_user_id: str = Form(...),
    log_session: str = Form(""),
) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件")
    imports_dir = ensure_output_dir("import")
    saved_path = imports_dir / ("import_{}_{}".format(int(time.time()), Path(csv_file.filename).name))
    with saved_path.open("wb") as handle:
        while True:
            chunk = await csv_file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    try:
        result = import_tools().import_clan_csv(saved_path, title, surname, actor)
        await csv_file.close()
        record_action(actor, log_session, "add-data", "import-csv:{}".format(result.get("clan_id", title)))
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/import/generated")
def import_generated(current_user_id: Optional[str] = None, total: Optional[int] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_admin(current_user_id)
    try:
        result = import_tools().import_generated_data(total=total, reset=True, creator_user_id="admin")
        record_action(actor, log_session, "add-data", "import-generated")
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/import/bundle")
async def import_bundle_file(
    bundle_file: UploadFile = File(...),
    current_user_id: str = Form(...),
    log_session: str = Form(""),
) -> Dict[str, Any]:
    actor = require_admin(current_user_id)
    if not bundle_file.filename or not bundle_file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="请上传 export.py 生成的 import_bundle.json")
    imports_dir = ensure_output_dir("import")
    saved_path = imports_dir / ("bundle_{}_{}".format(int(time.time()), Path(bundle_file.filename).name))
    with saved_path.open("wb") as handle:
        while True:
            chunk = await bundle_file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    try:
        result = import_tools().import_bundle(saved_path)
        await bundle_file.close()
        record_action(actor, log_session, "add-data", "import-bundle:{}".format(Path(bundle_file.filename).name))
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/export/database")
def export_database(current_user_id: Optional[str] = None) -> Dict[str, Any]:
    require_admin(current_user_id)
    try:
        return export_tools().export_database()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/export/clans")
def export_clans(payload: ExportClansRequest, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    if not payload.clan_ids:
        raise HTTPException(status_code=400, detail="请选择至少一个族谱")
    if actor != "admin":
        for clan_id in payload.clan_ids:
            if not service.clan_permission(clan_id, actor)["can_edit"]:
                raise HTTPException(status_code=403, detail="当前用户不能导出族谱 {}".format(clan_id))
    try:
        return export_tools().export_clans(payload.clan_ids)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/export/members/{member_id}")
def export_member(member_id: int, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    if actor != "admin" and not service.clan_permission(member_clan_id(member_id), actor)["can_edit"]:
        raise HTTPException(status_code=403, detail="当前用户不能导出该对象")
    try:
        return export_tools().export_member(member_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/performance/explain")
def performance_explain(payload: PerformanceExplainRequest, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    require_actor(current_user_id)
    try:
        return write_search_explain(payload.q, payload.clan_id, payload.performance_mode)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/collaborations", status_code=201)
def grant_collaboration(payload: CollaborationIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_owner(payload.clan_id, actor)
    result = service.grant_collaboration(payload)
    record_action(actor, log_session, "grant-access", "{}:{}".format(payload.clan_id, payload.user_id))
    return result


@app.delete("/api/collaborations")
def revoke_collaboration(payload: CollaborationIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_owner(payload.clan_id, actor)
    result = service.revoke_collaboration(payload)
    record_action(actor, log_session, "remove-access", "{}:{}".format(payload.clan_id, payload.user_id))
    return result


@app.post("/api/collaborations/revoke")
def revoke_collaboration_post(payload: CollaborationIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    return revoke_collaboration(payload, current_user_id=current_user_id, log_session=log_session)


@app.get("/api/dashboard")
def dashboard(clan_id: Optional[int] = None) -> Dict[str, Any]:
    if clan_id == 0:
        clan_id = None
    return service.dashboard(clan_id)


@app.get("/api/members")
def list_members(clan_id: int = 1, q: str = "") -> List[Dict[str, Any]]:
    return service.members(clan_id, q)


@app.get("/api/members/search-performance")
def search_members_with_metrics(
    clan_id: int = Query(0, ge=0),
    q: str = "",
    performance_mode: bool = False,
    current_user_id: Optional[str] = None,
    log_session: Optional[str] = None,
) -> Dict[str, Any]:
    result = measured_member_search(clan_id, q, performance_mode)
    record_action(current_user_id, log_session, "search-data", q or "empty")
    return result


@app.get("/api/members/{member_id}/detail")
def member_detail(member_id: int) -> Dict[str, Any]:
    return service.member_detail(member_id)


@app.post("/api/members", status_code=201)
def create_member(payload: MemberIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_edit(payload.clan_id, actor)
    result = service.create_member(payload)
    record_action(actor, log_session, "add-data", result.get("member_id", payload.name))
    return result


@app.put("/api/members/{member_id}")
def update_member(member_id: int, payload: MemberUpdate, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_edit(member_clan_id(member_id), actor)
    result = service.update_member(member_id, payload)
    record_action(actor, log_session, "add-data", member_id)
    return result


@app.post("/api/members/{member_id}/photo")
async def upload_member_photo(member_id: int, photo: UploadFile = File(...), current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_edit(member_clan_id(member_id), actor)
    if photo.content_type and not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只能上传图片文件")

    digest = hashlib.sha256()
    total_size = 0
    chunks: List[bytes] = []
    while True:
        chunk = await photo.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        chunks.append(chunk)
        digest.update(chunk)

    if total_size == 0:
        raise HTTPException(status_code=400, detail="上传图片不能为空")

    photo_hash = digest.hexdigest()
    member = service.update_member_photo_hash(member_id, photo_hash, b"".join(chunks), photo.content_type or "image/jpeg")
    record_action(actor, log_session, "add-data", "photo:{}".format(member_id))
    return {"ok": True, "member": member, "photo_sha256": photo_hash}


@app.get("/api/members/{member_id}/photo")
def get_member_photo(member_id: int) -> Response:
    photo_data = service.member_photo(member_id)
    if photo_data:
        content, content_type = photo_data
        return Response(content=content, media_type=content_type)
    default_path = APP_DIR / "resources" / "defaultpic.jpg"
    if not default_path.exists():
        raise HTTPException(status_code=404, detail="默认图片不存在")
    return Response(content=default_path.read_bytes(), media_type="image/jpeg")


@app.delete("/api/members/{member_id}", status_code=204)
def delete_member(member_id: int, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> None:
    actor = require_actor(current_user_id)
    require_clan_edit(member_clan_id(member_id), actor)
    service.delete_member(member_id)
    record_action(actor, log_session, "remove-data", member_id)


@app.get("/api/members/{member_id}/marriages")
def list_member_marriages(member_id: int, current_user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    require_actor(current_user_id)
    return service.member_marriages(member_id)


@app.post("/api/marriages", status_code=201)
def create_marriage(payload: MarriageIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_edit(member_clan_id(payload.member_id), actor)
    result = service.create_marriage(payload)
    record_action(actor, log_session, "add-data", "marriage:{}".format(result.get("marriage_id", "")))
    return result


@app.put("/api/marriages/{marriage_id}/divorce")
def set_marriage_divorce(marriage_id: int, payload: MarriageDivorceIn, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> Dict[str, Any]:
    actor = require_actor(current_user_id)
    require_clan_edit(marriage_clan_id(marriage_id), actor)
    result = service.set_divorce(marriage_id, payload)
    record_action(actor, log_session, "add-data", "marriage-divorce:{}".format(marriage_id))
    return result


@app.delete("/api/marriages/{marriage_id}", status_code=204)
def delete_marriage(marriage_id: int, current_user_id: Optional[str] = None, log_session: Optional[str] = None) -> None:
    actor = require_actor(current_user_id)
    require_clan_edit(marriage_clan_id(marriage_id), actor)
    service.delete_marriage(marriage_id)
    record_action(actor, log_session, "remove-data", "marriage:{}".format(marriage_id))


@app.get("/api/tree")
def tree(clan_id: int = 1, root_id: Optional[int] = None) -> Dict[str, Any]:
    return service.tree(clan_id, root_id)


@app.get("/api/members/{member_id}/ancestors")
def ancestors(member_id: int) -> List[Dict[str, Any]]:
    deputy_rows = deputy_ancestor_rows(member_id)
    if deputy_rows is not None:
        return deputy_rows
    return service.ancestors(member_id)


@app.get("/api/members/{member_id}/relationship")
def relationship(member_id: int, target_id: int = Query(..., gt=0)) -> Dict[str, Any]:
    deputy_path = deputy_relationship_path(member_id, target_id)
    if deputy_path is not None:
        return {"path": deputy_path}
    return {"path": service.relationship_path(member_id, target_id)}


@app.get("/api/query/spouse_children")
def query_spouse_children(member_id: Optional[int] = None, name: Optional[str] = None) -> Dict[str, Any]:
    member_id = resolve_query_member_id(member_id, name)
    member_rows = query_deputy_class(
        "father_down_edges",
        "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic "
        "FROM members WHERE member_id = {} LIMIT 1;".format(sql_literal(member_id)),
    )
    spouse_a_rows = query_deputy_class(
        "spouse_a_edges",
        "SELECT m.member_id,m.clan_id,m.name,m.gender,m.birth_year,m.death_year,m.father_id,m.mother_id,m.generation_num,m.bio,m.id_pic,"
        "se.marry_year,se.divorce_year "
        "FROM spouse_a_edges AS se JOIN members AS m ON m.member_id = se.to_member_id "
        "WHERE se.from_member_id = {} ORDER BY m.member_id;".format(sql_literal(member_id)),
    )
    spouse_b_rows = query_deputy_class(
        "spouse_b_edges",
        "SELECT m.member_id,m.clan_id,m.name,m.gender,m.birth_year,m.death_year,m.father_id,m.mother_id,m.generation_num,m.bio,m.id_pic,"
        "se.marry_year,se.divorce_year "
        "FROM spouse_b_edges AS se JOIN members AS m ON m.member_id = se.to_member_id "
        "WHERE se.from_member_id = {} ORDER BY m.member_id;".format(sql_literal(member_id)),
    )
    father_child_rows = query_deputy_class(
        "father_down_edges",
        "SELECT m.member_id,m.clan_id,m.name,m.gender,m.birth_year,m.death_year,m.father_id,m.mother_id,m.generation_num,m.bio,m.id_pic,"
        "'father' AS parent_role,'parent_child' AS edge_type "
        "FROM father_down_edges AS edge JOIN members AS m ON m.member_id = edge.to_member_id "
        "WHERE edge.from_member_id = {} ORDER BY m.birth_year,m.member_id;".format(sql_literal(member_id)),
    )
    mother_child_rows = query_deputy_class(
        "mother_down_edges",
        "SELECT m.member_id,m.clan_id,m.name,m.gender,m.birth_year,m.death_year,m.father_id,m.mother_id,m.generation_num,m.bio,m.id_pic,"
        "'mother' AS parent_role,'parent_child' AS edge_type "
        "FROM mother_down_edges AS edge JOIN members AS m ON m.member_id = edge.to_member_id "
        "WHERE edge.from_member_id = {} ORDER BY m.birth_year,m.member_id;".format(sql_literal(member_id)),
    )
    if (
        member_rows is not None
        and spouse_a_rows is not None
        and spouse_b_rows is not None
        and father_child_rows is not None
        and mother_child_rows is not None
    ):
        spouses_by_id = {}
        for row in spouse_a_rows + spouse_b_rows:
            spouses_by_id[int(row["member_id"])] = row
        children_by_id = {}
        for row in father_child_rows + mother_child_rows:
            children_by_id[int(row["member_id"])] = row
        return {
            "member": member_rows[0] if member_rows else {},
            "spouses": sorted(spouses_by_id.values(), key=lambda item: int(item["member_id"])),
            "children": sorted(children_by_id.values(), key=lambda item: (optional_row_int(item, "birth_year") or 9999, int(item["member_id"]))),
        }
    detail = service.member_detail(member_id)
    return {"member": detail["member"], "spouses": detail["spouses"], "children": detail["children"]}


@app.get("/api/query/ancestors")
def query_ancestors(member_id: Optional[int] = None, name: Optional[str] = None) -> List[Dict[str, Any]]:
    member_id = resolve_query_member_id(member_id, name)
    deputy_rows = deputy_ancestor_rows(member_id)
    if deputy_rows is not None:
        return deputy_rows
    return service.ancestors(member_id)


@app.get("/api/query/longevity")
def query_longevity(clan_id: int = Query(..., gt=0)) -> List[Dict[str, Any]]:
    groups: Dict[int, List[int]] = {}
    deputy_rows = query_deputy_class(
        "known_lifespan_members",
        "SELECT generation_num,lifespan FROM known_lifespan_members "
        "WHERE clan_id = {} AND generation_num IS NOT NULL;".format(sql_literal(clan_id)),
    )
    if deputy_rows is not None:
        for row in deputy_rows:
            generation = optional_row_int(row, "generation_num")
            lifespan = optional_row_int(row, "lifespan")
            if generation is not None and lifespan is not None:
                groups.setdefault(generation, []).append(lifespan)
    else:
        for row in all_member_rows(clan_id):
            generation = optional_row_int(row, "generation_num")
            age = row_age(row)
            if generation is not None and age is not None:
                groups.setdefault(generation, []).append(age)
    result = []
    for generation, ages in groups.items():
        result.append({
            "generation_num": generation,
            "avg_lifespan": round(sum(ages) / len(ages), 2),
            "member_count": len(ages),
        })
    return sorted(result, key=lambda item: item["avg_lifespan"], reverse=True)


@app.get("/api/query/singles")
def query_singles(clan_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if clan_id == 0:
        clan_id = None
    where = "WHERE clan_id = {}".format(sql_literal(clan_id)) if clan_id else ""
    deputy_rows = query_deputy_class(
        "male_50_plus",
        "SELECT member_id,clan_id,name,gender,birth_year,death_year,generation_num,age "
        "FROM male_50_plus {} ORDER BY clan_id,birth_year,member_id LIMIT 500;".format(where),
    )
    if deputy_rows is not None:
        marriage_where = "WHERE clan_id = {}".format(sql_literal(clan_id)) if clan_id else ""
        active_rows = query_deputy_class(
            "active_marriages",
            "SELECT spouse_a_id,spouse_b_id FROM active_marriages {};".format(marriage_where),
        )
        if active_rows is None:
            active_rows = []
        married_ids: Set[int] = set()
        for marriage in active_rows:
            spouse_a = optional_row_int(marriage, "spouse_a_id")
            spouse_b = optional_row_int(marriage, "spouse_b_id")
            if spouse_a:
                married_ids.add(spouse_a)
            if spouse_b:
                married_ids.add(spouse_b)
        result = []
        for row in deputy_rows:
            member_id = int(row["member_id"])
            if member_id not in married_ids:
                result.append(row)
        return result[:200]
    rows = all_member_rows(clan_id)
    result = []
    for row in rows:
        if row.get("gender") != "M":
            continue
        birth_year = optional_row_int(row, "birth_year")
        if not birth_year or optional_row_int(row, "death_year"):
            continue
        age = datetime.now().year - birth_year
        if age <= 50:
            continue
        member_id = int(row["member_id"])
        has_spouse = any(
            (optional_row_int(child, "father_id") == member_id and optional_row_int(child, "mother_id") is not None)
            or (optional_row_int(child, "mother_id") == member_id and optional_row_int(child, "father_id") is not None)
            for child in rows
        )
        if not has_spouse:
            result.append(merge_dict(row, {"age": age}))
    return sorted(result, key=lambda item: (int(item["clan_id"]), int(item["birth_year"])))[:200]


@app.get("/api/query/early_birth")
def query_early_birth(clan_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if clan_id == 0:
        clan_id = None
    rows = all_member_rows(clan_id)
    groups: Dict[Tuple[int, int], List[int]] = {}
    for row in rows:
        current_clan = optional_row_int(row, "clan_id")
        generation = optional_row_int(row, "generation_num")
        birth_year = optional_row_int(row, "birth_year")
        if current_clan is not None and generation is not None and birth_year is not None:
            groups.setdefault((current_clan, generation), []).append(birth_year)
    averages = {key: sum(values) / len(values) for key, values in groups.items()}
    result = []
    for row in rows:
        current_clan = optional_row_int(row, "clan_id")
        generation = optional_row_int(row, "generation_num")
        birth_year = optional_row_int(row, "birth_year")
        key = (current_clan, generation)
        if current_clan is None or generation is None or birth_year is None or key not in averages:
            continue
        avg_birth = averages[key]
        if birth_year < avg_birth:
            result.append(merge_dict(row, {
                "avg_birth_year": round(avg_birth, 2),
                "years_before_avg": round(avg_birth - birth_year, 2),
            }))
    return sorted(result, key=lambda item: (int(item["clan_id"]), int(item.get("generation_num") or 0), int(item["birth_year"])))[:300]


@app.get("/api/query/great_grandchildren")
def query_great_grandchildren(member_id: Optional[int] = None, name: Optional[str] = None) -> List[Dict[str, Any]]:
    member_id = resolve_query_member_id(member_id, name)
    deputy_rows = deputy_great_grandchildren_rows(member_id)
    if deputy_rows is not None:
        return deputy_rows
    rows = all_member_rows()
    by_parent: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        for parent_key in ("father_id", "mother_id"):
            parent_id = optional_row_int(row, parent_key)
            if parent_id:
                by_parent.setdefault(parent_id, []).append(row)
    generation = [row for row in by_parent.get(member_id, [])]
    for _ in range(2):
        next_generation = []
        for row in generation:
            next_generation.extend(by_parent.get(int(row["member_id"]), []))
        generation = next_generation
    unique = {int(row["member_id"]): row for row in generation}
    return sorted(unique.values(), key=lambda item: int(item["member_id"]))[:300]


@app.post("/api/invitations", status_code=201)
def invite(payload: InvitationIn, current_user_id: Optional[str] = None) -> Dict[str, Any]:
    require_clan_owner(payload.clan_id, current_user_id)
    return service.grant_collaboration(CollaborationIn(clan_id=payload.clan_id, user_id=payload.user_id))
