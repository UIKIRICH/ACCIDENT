"""
事故处理平台 - 数据库层（SQLAlchemy ORM）
支持 SQLite 和 MySQL 无缝切换。

使用方式：
  - SQLite（默认）：无需配置，自动使用 accident_platform.db
  - MySQL：设置环境变量 DATABASE_URL=mysql+pymysql://user:pass@host:port/dbname
"""
import json
import os
import uuid
import hashlib
import base64
import hmac
import time as time_module
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import bcrypt

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, ForeignKey,
    UniqueConstraint, Table, MetaData, text, inspect
)
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# 路径 & 数据库连接
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent.absolute()

# 从环境变量读取 DATABASE_URL，默认 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'accident_platform.db'}")

# SQLite 需要 check_same_thread=False 以支持多线程
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------------------------------------------------------
# ORM 模型定义（Task 2：SQLAlchemy ORM）
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False, default="")
    role = Column(String(50), nullable=False, default="analyst")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class Case(Base):
    __tablename__ = "cases"
    id = Column(String(255), primary_key=True)
    title = Column(String(255), nullable=False, default="")
    accident_type = Column(String(255), nullable=False, default="")
    location = Column(String(255), nullable=False, default="")
    status = Column(String(50), nullable=False, default="待处理")
    description = Column(Text, nullable=False, default="")
    weather = Column(String(100), nullable=False, default="")
    road_env = Column(String(255), nullable=False, default="")
    vehicle_info = Column(Text, nullable=False, default="[]")
    priority = Column(String(50), nullable=False, default="中")
    reviewer = Column(String(100), nullable=False, default="")
    submitted_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    eta = Column(String(100), nullable=False, default="")


class CaseSnapshot(Base):
    __tablename__ = "case_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    step = Column(String(100), nullable=False, default="")
    form_data = Column(Text, nullable=False, default="{}")
    analysis = Column(Text, nullable=False, default="{}")
    recommendation = Column(Text, nullable=False, default="{}")
    rule_basis = Column(Text, nullable=False, default="{}")
    manual_review = Column(Text, nullable=False, default="{}")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class Rule(Base):
    __tablename__ = "rules"
    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(String(100), nullable=False, default="")
    scene = Column(String(255), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    status = Column(String(50), nullable=False, default="启用")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(String(255), primary_key=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False, default="")
    task_type = Column(String(100), nullable=False, default="")
    status = Column(String(50), nullable=False, default="pending")
    priority = Column(String(50), nullable=False, default="medium")
    deadline = Column(String(30), nullable=True)
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    assignee = Column(Integer, ForeignKey("users.id"), nullable=True)


class VideoMetadata(Base):
    __tablename__ = "video_metadata"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String(255), nullable=False, default="")
    file_size = Column(Integer, nullable=False, default=0)
    duration = Column(Float, nullable=False, default=0.0)
    keyframe_count = Column(Integer, nullable=False, default=0)
    extra_data = Column(Text, nullable=False, default="{}")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class Keyframe(Base):
    __tablename__ = "keyframes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    video_id = Column(Integer, ForeignKey("video_metadata.id", ondelete="SET NULL"), nullable=True)
    frame_index = Column(Integer, nullable=False, default=0)
    timestamp = Column(Float, nullable=False, default=0.0)
    image_path = Column(String(500), nullable=False, default="")
    score = Column(Float, nullable=False, default=0.0)
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class LiabilityResult(Base):
    __tablename__ = "liability_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    summary = Column(Text, nullable=False, default="")
    ratio = Column(String(100), nullable=False, default="")
    details = Column(Text, nullable=False, default="{}")
    hit_rules = Column(Text, nullable=False, default="[]")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String(100), nullable=False, default="standard")
    content = Column(Text, nullable=False, default="{}")
    status = Column(String(50), nullable=False, default="draft")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

class Evidence(Base):
    __tablename__ = "evidences"
    evidence_id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    evidence_type = Column(String(50), nullable=False, default="image")
    file_path = Column(String(500), nullable=False, default="")
    upload_time = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    analysis_status = Column(String(50), nullable=False, default="pending")
    related_stage = Column(String(100), nullable=False, default="")
    extra_data = Column(Text, nullable=False, default="{}")


class MatchedRule(Base):
    __tablename__ = "matched_rules"
    match_id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(String(255), nullable=False, default="")
    rule_name = Column(String(255), nullable=False, default="")
    trigger_condition = Column(Text, nullable=False, default="")
    trigger_reason = Column(Text, nullable=False, default="")
    legal_basis = Column(Text, nullable=False, default="")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class Review(Base):
    __tablename__ = "reviews"
    review_id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    reviewer = Column(String(100), nullable=False, default="")
    system_suggestion = Column(Text, nullable=False, default="")
    final_result = Column(Text, nullable=False, default="")
    review_comment = Column(Text, nullable=False, default="")
    review_time = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class AnalysisTask(Base):
    """分析任务表（Task 4）"""
    __tablename__ = "analysis_tasks"
    task_id = Column(String(255), primary_key=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    task_type = Column(String(50), nullable=False, default="image")
    task_status = Column(String(50), nullable=False, default="pending")
    progress = Column(Integer, nullable=False, default=0)
    result_json = Column(Text, nullable=False, default="{}")
    error_message = Column(Text, nullable=False, default="")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class OperationLog(Base):
    """操作审计日志表（Task 6）"""
    __tablename__ = "operation_logs"
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action_type = Column(String(100), nullable=False)
    target_type = Column(String(100), nullable=False)
    target_id = Column(String(255), nullable=True)
    before_data = Column(Text, nullable=True)
    after_data = Column(Text, nullable=True)
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class AnalysisVersion(Base):
    """责任结果版本管理表（Task 7）"""
    __tablename__ = "analysis_versions"
    version_id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    version_no = Column(Integer, nullable=False)
    facts_json = Column(Text, nullable=False, default="{}")
    matched_rules_json = Column(Text, nullable=False, default="[]")
    suggestion_json = Column(Text, nullable=False, default="{}")
    model_version = Column(String(100), nullable=False, default="")
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class StructuredFact(Base):
    """结构化事实表 - 证据来源追踪（Task 8）"""
    __tablename__ = "structured_facts"
    fact_id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(255), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(50), nullable=False)
    fact_type = Column(String(100), nullable=False)
    fact_value = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    evidence_id = Column(Integer, ForeignKey("evidences.evidence_id", ondelete="SET NULL"), nullable=True)
    keyframe_time = Column(Float, nullable=True)
    created_at = Column(String(30), nullable=False, default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ---------------------------------------------------------------------------
# 数据库会话依赖
# ---------------------------------------------------------------------------

def get_db() -> Session:
    """获取 SQLAlchemy 数据库会话。"""
    db = SessionLocal()
    return db


def get_db_conn():
    """
    获取原生数据库连接（兼容旧版直接 execute SQL）。
    仅用于 main.py 中遗留的 raw SQL 查询。
    """
    if DATABASE_URL.startswith("sqlite"):
        import sqlite3
        db_path = DATABASE_URL.replace("sqlite:///", "")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    else:
        # For MySQL, use raw connection from engine
        raw_conn = engine.raw_connection()
        return raw_conn


def init_db():
    """初始化数据库：创建所有表 + 默认数据。"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 从环境变量读取默认管理员账号密码（可选）
        default_admin_username = os.getenv("DEFAULT_ADMIN_USERNAME", "").strip()
        default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "").strip()
        if default_admin_username and default_admin_password:
            existing = db.query(User).filter(User.username == default_admin_username).first()
            if not existing:
                pw_hash = _hash_password(default_admin_password)
                db.add(User(username=default_admin_username, password_hash=pw_hash, display_name="系统管理员", role="admin"))
                print(f"[DB] Created default admin user: {default_admin_username}")
                db.commit()

        # 检查是否有默认管理员 (fallback: admin/admin123)
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            password_hash = _hash_password("admin123")
            db.add(User(username="admin", password_hash=password_hash, display_name="系统管理员", role="admin"))
            password_hash2 = _hash_password("analyst123")
            db.add(User(username="analyst", password_hash=password_hash2, display_name="分析员", role="analyst"))
            db.commit()

        # 检查是否有默认规则
        rule_count = db.query(Rule).count()
        if rule_count == 0:
            default_rules = [
                ("R-001", "后车未保持安全距离", "追尾事故", "同向行驶", "后车与前车的距离不足安全距离（至少3秒车距），造成追尾事故，后车负全部责任。"),
                ("R-002", "变道未打转向灯", "变道事故", "车道变更", "变更车道时未提前开启转向灯，影响其他车辆正常行驶，变道车辆负主要责任。"),
                ("R-003", "闯红灯行为", "路口事故", "交叉路口", "违反交通信号灯指示，闯红灯造成事故，闯红灯车辆负全部责任。"),
                ("R-004", "倒车未观察", "倒车事故", "停车场/倒车", "倒车时未仔细观察后方情况，造成碰撞事故，倒车方负全部责任。"),
                ("R-005", "超速行驶", "一般事故", "限速路段", "超过规定速度行驶，导致制动距离不足或失控，超速车辆根据情节承担相应责任。"),
                ("R-006", "逆行", "一般事故", "单行道", "机动车逆向行驶，与对向正常行驶车辆相撞，逆行车辆负全部责任。"),
                ("R-007", "违法变更车道", "变道事故", "车道变更", "连续变更两条以上车道，或在不具备变道条件时强行变道，变道车辆负主要责任。"),
            ]
            for rid, rname, rtype, rscene, rcontent in default_rules:
                db.add(Rule(id=rid, name=rname, type=rtype, scene=rscene, content=rcontent))
            db.commit()

        print(f"[DB] Database initialized ({DATABASE_URL})")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 密码 / Token 工具
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "accident-platform-secret-key-change-in-production")

# JWT 过期时间（小时），可通过环境变量配置
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


def _hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """使用 bcrypt 验证密码"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: int, role: str, display_name: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "display_name": display_name,
        "exp": int(time_module.time()) + 3600 * JWT_EXPIRE_HOURS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "==").decode())
        if payload.get("exp", 0) < time_module.time():
            return None
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def row_to_dict(row) -> Dict[str, Any]:
    """Convert SQLAlchemy model instance to dict."""
    if row is None:
        return None
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def rows_to_list(rows) -> List[Dict[str, Any]]:
    """Convert list of SQLAlchemy model instances to list of dict."""
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user and verify_password(password, user.password_hash):
            user_dict = row_to_dict(user)
            token = create_token(user_dict["id"], user_dict["role"], user_dict["display_name"])
            return {"user": user_dict, "token": token}
        return None
    finally:
        db.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "created_at": user.created_at,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Case CRUD
# ---------------------------------------------------------------------------

def create_case(data: Dict[str, Any], user_id: int = None) -> Dict[str, Any]:
    case_id = data.get("id") or f"ACC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
    db = get_db()
    try:
        case = Case(
            id=case_id,
            title=data.get("title", ""),
            accident_type=data.get("accident_type", data.get("accidentType", "")),
            location=data.get("location", ""),
            status=data.get("status", "待处理"),
            description=data.get("description", ""),
            weather=data.get("weather", ""),
            road_env=data.get("road_env", data.get("roadEnv", "")),
            vehicle_info=json.dumps(data.get("vehicles", data.get("vehicle_info", [])), ensure_ascii=False),
            priority=data.get("priority", "中"),
            created_by=user_id,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return row_to_dict(case)
    finally:
        db.close()


def get_cases(params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    params = params or {}
    db = get_db()
    try:
        query = db.query(Case)
        if params.get("status"):
            query = query.filter(Case.status == params["status"])
        if params.get("accident_type"):
            query = query.filter(Case.accident_type == params["accident_type"])
        query = query.order_by(Case.submitted_at.desc())
        limit = params.get("limit")
        if limit:
            query = query.limit(int(limit))
        return rows_to_list(query.all())
    finally:
        db.close()


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return None
        result = row_to_dict(case)
        # Parse JSON fields
        if isinstance(result.get("vehicle_info"), str):
            try:
                result["vehicle_info"] = json.loads(result["vehicle_info"])
            except (json.JSONDecodeError, TypeError):
                result["vehicle_info"] = []

        # Get snapshot
        snapshot = db.query(CaseSnapshot).filter(
            CaseSnapshot.case_id == case_id
        ).order_by(CaseSnapshot.created_at.desc()).first()
        if snapshot:
            snap_dict = row_to_dict(snapshot)
            for field in ["form_data", "analysis", "recommendation", "rule_basis", "manual_review"]:
                if isinstance(snap_dict.get(field), str):
                    try:
                        snap_dict[field] = json.loads(snap_dict[field])
                    except (json.JSONDecodeError, TypeError):
                        snap_dict[field] = {}
            result["snapshot"] = snap_dict

        # Get liability results
        liability = db.query(LiabilityResult).filter(
            LiabilityResult.case_id == case_id
        ).order_by(LiabilityResult.created_at.desc()).first()
        if liability:
            liab_dict = row_to_dict(liability)
            for field in ["details", "hit_rules"]:
                if isinstance(liab_dict.get(field), str):
                    try:
                        liab_dict[field] = json.loads(liab_dict[field])
                    except (json.JSONDecodeError, TypeError):
                        liab_dict[field] = {} if field == "details" else []
            result["liability"] = liab_dict

        return result
    finally:
        db.close()


def update_case(case_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed_fields = {
        "title", "accident_type", "location", "status", "description",
        "weather", "road_env", "priority", "reviewer", "eta",
    }
    db = get_db()
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return None
        for k, v in updates.items():
            if k in allowed_fields:
                setattr(case, k, v)
        case.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
        return get_case(case_id)
    finally:
        db.close()


def delete_case(case_id: str) -> bool:
    db = get_db()
    try:
        case = db.query(Case).filter(Case.id == case_id).first()
        if case:
            db.delete(case)
            db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Snapshot CRUD
# ---------------------------------------------------------------------------

def save_case_snapshot(case_id: str, step: str, data: Dict[str, Any]):
    db = get_db()
    try:
        snapshot = CaseSnapshot(
            case_id=case_id,
            step=step,
            form_data=json.dumps(data.get("form", {}), ensure_ascii=False),
            analysis=json.dumps(data.get("analysis", {}), ensure_ascii=False),
            recommendation=json.dumps(data.get("recommendation", {}), ensure_ascii=False),
            rule_basis=json.dumps(data.get("ruleBasis", {}), ensure_ascii=False),
            manual_review=json.dumps(data.get("manualReview", {}), ensure_ascii=False),
        )
        db.add(snapshot)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------

def get_rules(params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    params = params or {}
    db = get_db()
    try:
        query = db.query(Rule)
        if params.get("type"):
            query = query.filter(Rule.type == params["type"])
        if params.get("status"):
            query = query.filter(Rule.status == params["status"])
        query = query.order_by(Rule.id.asc())
        return rows_to_list(query.all())
    finally:
        db.close()


def get_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    try:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        return row_to_dict(rule)
    finally:
        db.close()


def create_rule(data: Dict[str, Any], user_id: int = None) -> Dict[str, Any]:
    db = get_db()
    try:
        last = db.query(Rule).order_by(Rule.id.desc()).first()
        if last:
            last_num = int(last.id.split("-")[1])
            new_id = f"R-{last_num + 1:03d}"
        else:
            new_id = "R-001"
        rule = Rule(
            id=new_id,
            name=data["name"],
            type=data.get("type", ""),
            scene=data.get("scene", ""),
            content=data.get("content", ""),
            status=data.get("status", "启用"),
            created_by=user_id,
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return row_to_dict(rule)
    finally:
        db.close()


def update_rule(rule_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed_fields = {"name", "type", "scene", "content", "status"}
    db = get_db()
    try:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if not rule:
            return None
        for k, v in updates.items():
            if k in allowed_fields:
                setattr(rule, k, v)
        rule.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
        return row_to_dict(rule)
    finally:
        db.close()


def delete_rule(rule_id: str) -> bool:
    db = get_db()
    try:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if rule:
            db.delete(rule)
            db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tasks CRUD
# ---------------------------------------------------------------------------

def get_tasks(params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    params = params or {}
    db = get_db()
    try:
        query = db.query(Task)
        if params.get("status"):
            query = query.filter(Task.status == params["status"])
        if params.get("task_type"):
            query = query.filter(Task.task_type == params["task_type"])
        query = query.order_by(Task.created_at.desc())
        results = rows_to_list(query.all())
        # Enrich with case title
        for r in results:
            c = db.query(Case).filter(Case.id == r["case_id"]).first()
            r["case_title"] = c.title if c else ""
        return results
    finally:
        db.close()


def create_task(data: Dict[str, Any]) -> Dict[str, Any]:
    task_id = f"T-{uuid.uuid4().hex[:6].upper()}"
    db = get_db()
    try:
        task = Task(
            id=task_id,
            case_id=data["case_id"],
            title=data.get("title", ""),
            task_type=data.get("task_type", "general"),
            status=data.get("status", "pending"),
            priority=data.get("priority", "medium"),
            deadline=data.get("deadline"),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return row_to_dict(task)
    finally:
        db.close()


def complete_task(task_id: str) -> bool:
    db = get_db()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = "completed"
            task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.commit()
        return True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> Dict[str, Any]:
    db = get_db()
    try:
        total_cases = db.query(Case).count()
        pending = db.query(Case).filter(
            (Case.status == "待处理") | (Case.status == "处理中")
        ).count()
        pending_analysis = db.query(Case).filter(Case.status == "待分析").count()
        pending_review = db.query(Case).filter(Case.status == "待复核").count()
        completed = db.query(Case).filter(Case.status == "已完成").count()
        pending_tasks = db.query(Task).filter(Task.status == "pending").count()
        active_rules = db.query(Rule).filter(Rule.status == "启用").count()

        # Today's new cases
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_new = db.query(Case).filter(Case.submitted_at.like(f"{today_str}%")).count()

        # Weekly trend (last 7 days)
        from sqlalchemy import func
        weekly_trend_raw = db.query(
            Case.submitted_at, func.count(Case.id)
        ).filter(
            Case.submitted_at >= (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        ).group_by(
            Case.submitted_at
        ).order_by(Case.submitted_at).all()

        # Aggregate by day
        day_counts = {}
        for row in weekly_trend_raw:
            day = row[0][:10] if row[0] else ""
            day_counts[day] = day_counts.get(day, 0) + row[1]
        weekly_trend = [{"day": k, "cnt": v} for k, v in sorted(day_counts.items())]

        return {
            "totalCases": total_cases,
            "pendingCases": pending,
            "pendingAnalysis": pending_analysis,
            "pendingReview": pending_review,
            "completedCases": completed,
            "pendingTasks": pending_tasks,
            "activeRules": active_rules,
            "todayNew": today_new,
            "weeklyTrend": weekly_trend,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# History Cases
# ---------------------------------------------------------------------------

def get_history_cases(params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    params = params or {}
    db = get_db()
    try:
        query = db.query(Case).filter(
            Case.status.in_(["已完成", "待复核", "待分析"])
        )
        if params.get("status"):
            query = query.filter(Case.status == params["status"])
        query = query.order_by(Case.submitted_at.desc())
        limit = params.get("limit")
        if limit:
            query = query.limit(int(limit))
        return rows_to_list(query.all())
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Liability Results
# ---------------------------------------------------------------------------

def save_liability_result(case_id: str, data: Dict[str, Any]):
    db = get_db()
    try:
        # 1. Upsert liability_results
        existing = db.query(LiabilityResult).filter(
            LiabilityResult.case_id == case_id
        ).order_by(LiabilityResult.created_at.desc()).first()

        hit_rules_json = json.dumps(data.get("hit_rules", []), ensure_ascii=False)

        if existing:
            existing.summary = data.get("summary", "")
            existing.ratio = data.get("ratio", "")
            existing.details = json.dumps(data.get("details", {}), ensure_ascii=False)
            existing.hit_rules = hit_rules_json
        else:
            liability = LiabilityResult(
                case_id=case_id,
                summary=data.get("summary", ""),
                ratio=data.get("ratio", ""),
                details=json.dumps(data.get("details", {}), ensure_ascii=False),
                hit_rules=hit_rules_json,
            )
            db.add(liability)

        # 2. Sync matched_rules
        db.query(MatchedRule).filter(MatchedRule.case_id == case_id).delete()

        hit_rules = data.get("hit_rules", [])
        if isinstance(hit_rules, list):
            for rule in hit_rules:
                if not isinstance(rule, dict):
                    continue
                rule_id = rule.get("code") or rule.get("rule_id") or ""
                rule_name = rule.get("name") or rule.get("rule_name") or ""
                trigger_condition = rule.get("trigger_condition", "")
                trigger_reason = rule.get("trigger_reason", "")
                legal_basis = rule.get("content") or rule.get("legal_basis") or ""
                mr = MatchedRule(
                    case_id=case_id,
                    rule_id=rule_id,
                    rule_name=rule_name,
                    trigger_condition=trigger_condition,
                    trigger_reason=trigger_reason,
                    legal_basis=legal_basis,
                )
                db.add(mr)

        db.commit()
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"保存责任判定失败: {str(e)}") from e
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Video Metadata
# ---------------------------------------------------------------------------

def save_video_metadata(case_id: str, data: Dict[str, Any]):
    db = get_db()
    try:
        vm = VideoMetadata(
            case_id=case_id,
            file_name=data.get("file_name", ""),
            file_size=data.get("file_size", 0),
            duration=data.get("duration", 0.0),
            keyframe_count=data.get("keyframe_count", 0),
            metadata=json.dumps(data.get("metadata", {}), ensure_ascii=False),
        )
        db.add(vm)
        db.commit()
    finally:
        db.close()


# ================================================================
# Task 3: Evidence CRUD
# ================================================================

def create_evidence_record(case_id: str, evidence_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建证据记录"""
    db = get_db()
    try:
        ev = Evidence(
            case_id=case_id,
            evidence_type=evidence_data.get("evidence_type", "image"),
            file_path=evidence_data.get("file_path", ""),
            analysis_status=evidence_data.get("analysis_status", "pending"),
            related_stage=evidence_data.get("related_stage", ""),
            metadata=json.dumps(evidence_data.get("metadata", {}), ensure_ascii=False),
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return row_to_dict(ev)
    finally:
        db.close()


def get_case_evidences(case_id: str) -> List[Dict[str, Any]]:
    """获取案件所有证据"""
    db = get_db()
    try:
        evidences = db.query(Evidence).filter(Evidence.case_id == case_id).order_by(Evidence.upload_time.desc()).all()
        return rows_to_list(evidences)
    finally:
        db.close()


# ================================================================
# Task 4: Analysis Task CRUD
# ================================================================

def create_analysis_task(case_id: str, task_type: str) -> Dict[str, Any]:
    """创建分析任务"""
    task_id = f"AT-{uuid.uuid4().hex[:8].upper()}"
    db = get_db()
    try:
        task = AnalysisTask(
            task_id=task_id,
            case_id=case_id,
            task_type=task_type,
            task_status="pending",
            progress=0,
            result_json="{}",
            error_message="",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return row_to_dict(task)
    finally:
        db.close()


def get_analysis_task(task_id: str) -> Optional[Dict[str, Any]]:
    """获取分析任务状态"""
    db = get_db()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.task_id == task_id).first()
        return row_to_dict(task)
    finally:
        db.close()


def update_analysis_task(task_id: str, updates: Dict[str, Any]) -> bool:
    """更新分析任务"""
    db = get_db()
    try:
        task = db.query(AnalysisTask).filter(AnalysisTask.task_id == task_id).first()
        if not task:
            return False
        for key in ["task_status", "progress", "result_json", "error_message"]:
            if key in updates:
                setattr(task, key, updates[key])
        task.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
        return True
    finally:
        db.close()


# ================================================================
# Task 5: State Machine
# ================================================================

# 状态常量
CASE_STATUS_DRAFT = "草稿"
CASE_STATUS_UPLOADED = "待分析"
CASE_STATUS_PROCESSING = "处理中"
CASE_STATUS_ANALYZED = "待复核"
CASE_STATUS_PENDING_REVIEW = "复核中"
CASE_STATUS_REVIEWED = "已复核"
CASE_STATUS_ARCHIVED = "已完成"
CASE_STATUS_FAILED = "失败"

# 状态流转规则: (当前状态, 目标状态) -> 是否允许
CASE_STATE_TRANSITIONS = {
    (None, CASE_STATUS_DRAFT): True,
    (CASE_STATUS_DRAFT, CASE_STATUS_UPLOADED): True,
    (CASE_STATUS_UPLOADED, CASE_STATUS_PROCESSING): True,
    (CASE_STATUS_UPLOADED, CASE_STATUS_UPLOADED): True,
    (CASE_STATUS_UPLOADED, CASE_STATUS_ANALYZED): True,
    (CASE_STATUS_PROCESSING, CASE_STATUS_ANALYZED): True,
    (CASE_STATUS_ANALYZED, CASE_STATUS_PENDING_REVIEW): True,
    (CASE_STATUS_PENDING_REVIEW, CASE_STATUS_REVIEWED): True,
    (CASE_STATUS_REVIEWED, CASE_STATUS_ARCHIVED): True,
    # 任何状态都可以失败
    (None, CASE_STATUS_FAILED): True,
    (CASE_STATUS_DRAFT, CASE_STATUS_FAILED): True,
    (CASE_STATUS_UPLOADED, CASE_STATUS_FAILED): True,
    (CASE_STATUS_PROCESSING, CASE_STATUS_FAILED): True,
    (CASE_STATUS_ANALYZED, CASE_STATUS_FAILED): True,
    (CASE_STATUS_PENDING_REVIEW, CASE_STATUS_FAILED): True,
    (CASE_STATUS_REVIEWED, CASE_STATUS_FAILED): True,
    # 允许回退到草稿（编辑）
    (CASE_STATUS_UPLOADED, CASE_STATUS_DRAFT): True,
    (CASE_STATUS_PROCESSING, CASE_STATUS_UPLOADED): True,
    # 已归档不可再改
}

def validate_case_status_transition(current_status: Optional[str], new_status: str) -> bool:
    """验证案件状态流转是否合法"""
    transition_key = (current_status, new_status)
    if transition_key in CASE_STATE_TRANSITIONS:
        return True
    # Allow any status → FAILED
    if new_status == CASE_STATUS_FAILED:
        return True
    # Allow transition between legacy and new statuses for same logical state
    legacy_map = {
        "待处理": CASE_STATUS_UPLOADED,
        "待分析": CASE_STATUS_UPLOADED,
        "待复核": CASE_STATUS_ANALYZED,
        "复核中": CASE_STATUS_PENDING_REVIEW,
        "已完成": CASE_STATUS_ARCHIVED,
    }
    mapped_current = legacy_map.get(current_status, current_status)
    mapped_new = legacy_map.get(new_status, new_status)
    return CASE_STATE_TRANSITIONS.get((mapped_current, mapped_new), False)


# ================================================================
# Task 6: Operation Log
# ================================================================

def create_operation_log(
    action_type: str,
    target_type: str,
    target_id: str = None,
    case_id: str = None,
    user_id: int = None,
    before_data: str = None,
    after_data: str = None,
):
    """创建操作审计日志"""
    db = get_db()
    try:
        log = OperationLog(
            case_id=case_id,
            user_id=user_id,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_data=before_data,
            after_data=after_data,
        )
        db.add(log)
        db.commit()
    finally:
        db.close()


# ================================================================
# Task 7: Analysis Versions
# ================================================================

def create_analysis_version(
    case_id: str,
    facts_json: str = "{}",
    matched_rules_json: str = "[]",
    suggestion_json: str = "{}",
    model_version: str = "",
) -> Dict[str, Any]:
    """创建新版本记录"""
    db = get_db()
    try:
        # 查询当前最大版本号
        max_version = db.query(AnalysisVersion.version_no).filter(
            AnalysisVersion.case_id == case_id
        ).order_by(AnalysisVersion.version_no.desc()).first()
        version_no = (max_version[0] + 1) if max_version else 1

        av = AnalysisVersion(
            case_id=case_id,
            version_no=version_no,
            facts_json=facts_json,
            matched_rules_json=matched_rules_json,
            suggestion_json=suggestion_json,
            model_version=model_version,
        )
        db.add(av)
        db.commit()
        db.refresh(av)
        return row_to_dict(av)
    finally:
        db.close()


def get_latest_analysis_version(case_id: str) -> Optional[Dict[str, Any]]:
    """获取最新版本"""
    db = get_db()
    try:
        av = db.query(AnalysisVersion).filter(
            AnalysisVersion.case_id == case_id
        ).order_by(AnalysisVersion.version_no.desc()).first()
        return row_to_dict(av)
    finally:
        db.close()


def get_analysis_versions(case_id: str) -> List[Dict[str, Any]]:
    """获取所有版本"""
    db = get_db()
    try:
        versions = db.query(AnalysisVersion).filter(
            AnalysisVersion.case_id == case_id
        ).order_by(AnalysisVersion.version_no.desc()).all()
        return rows_to_list(versions)
    finally:
        db.close()


# ================================================================
# Task 8: Structured Facts
# ================================================================

def create_structured_fact(
    case_id: str,
    source_type: str,
    fact_type: str,
    fact_value: str,
    confidence: float = 0.0,
    evidence_id: int = None,
    keyframe_time: float = None,
) -> Dict[str, Any]:
    """创建结构化事实"""
    db = get_db()
    try:
        sf = StructuredFact(
            case_id=case_id,
            source_type=source_type,
            fact_type=fact_type,
            fact_value=fact_value,
            confidence=confidence,
            evidence_id=evidence_id,
            keyframe_time=keyframe_time,
        )
        db.add(sf)
        db.commit()
        db.refresh(sf)
        return row_to_dict(sf)
    finally:
        db.close()


def get_case_structured_facts(case_id: str) -> List[Dict[str, Any]]:
    """获取案件所有结构化事实"""
    db = get_db()
    try:
        facts = db.query(StructuredFact).filter(
            StructuredFact.case_id == case_id
        ).order_by(StructuredFact.created_at.desc()).all()
        return rows_to_list(facts)
    finally:
        db.close()


# ================================================================
# Task 9: Evidence Consistency Check
# ================================================================

def get_evidence_consistency_check(case_id: str) -> Dict[str, Any]:
    """证据一致性检测"""
    db = get_db()
    try:
        facts = db.query(StructuredFact).filter(
            StructuredFact.case_id == case_id
        ).all()
        if not facts:
            return {"consistent": True, "score": 1.0, "conflicts": []}

        # 按 fact_type 分组比较不同 source_type 的值
        fact_groups = {}  # fact_type -> {source_type: [facts]}
        for f in facts:
            key = f.fact_type
            if key not in fact_groups:
                fact_groups[key] = {}
            src = f.source_type
            if src not in fact_groups[key]:
                fact_groups[key][src] = []
            fact_groups[key][src].append(f)

        conflicts = []
        total_checks = 0
        consistent_checks = 0

        for fact_type, sources in fact_groups.items():
            if len(sources) < 2:
                continue
            source_items = list(sources.items())
            for i in range(len(source_items)):
                for j in range(i + 1, len(source_items)):
                    src1, facts1 = source_items[i]
                    src2, facts2 = source_items[j]
                    for f1 in facts1:
                        for f2 in facts2:
                            total_checks += 1
                            if f1.fact_value.strip().lower() == f2.fact_value.strip().lower():
                                consistent_checks += 1
                            else:
                                conflicts.append({
                                    "fact_type": fact_type,
                                    "source_a": src1,
                                    "value_a": f1.fact_value,
                                    "source_b": src2,
                                    "value_b": f2.fact_value,
                                    "confidence_a": f1.confidence,
                                    "confidence_b": f2.confidence,
                                })

        score = consistent_checks / total_checks if total_checks > 0 else 1.0
        return {
            "consistent": score >= 0.6,
            "score": round(score, 2),
            "conflicts": conflicts[:20],  # 最多返回20条冲突
        }
    finally:
        db.close()