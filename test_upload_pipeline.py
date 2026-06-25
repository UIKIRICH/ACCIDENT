"""
自动化测试：视频上传 → 数据库写入完整性验证

用法：
    python test_upload_pipeline.py

前提：
    - 后端运行在 http://127.0.0.1:8001
    - backend/uploaded_videos/ 下存在可用的 .mp4 文件
"""

import os
import sys
import json
import time
import uuid
import tempfile
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image

BASE_URL = "http://127.0.0.1:8001"
PROJECT_DIR = Path(__file__).parent.absolute()
VIDEO_DIR = PROJECT_DIR / "backend" / "uploaded_videos"

# ── 辅助函数 ──
def green(s):  return f"\033[92m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def bold(s):   return f"\033[1m{s}\033[0m"
def ok(msg):   print(green(f"  ✓ {msg}"))
def fail(msg): print(red(f"  ✗ {msg}"))

results = {"pass": 0, "fail": 0}

def check(condition, label):
    if condition:
        ok(label)
        results["pass"] += 1
    else:
        fail(label)
        results["fail"] += 1

def api_get(path):
    return requests.get(f"{BASE_URL}{path}", timeout=30)

def api_delete(path):
    return requests.delete(f"{BASE_URL}{path}", timeout=30)

# ── 生成一张测试图片 ──
def make_test_image() -> BytesIO:
    img = Image.new("RGB", (640, 480), color=(255, 100, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    buf.name = "test_scene.jpg"
    return buf

# ── 测试 1: 上传视频 → 验证自动创建案件 + 证据 + 关键帧 + 融合证据 ──
def test_video_upload():
    print(bold("\n── 测试 1: 上传视频 → 数据库完整性 ──"))

    videos = sorted(VIDEO_DIR.glob("*.mp4"), key=lambda p: p.stat().st_size)
    if not videos:
        fail("没有可用的测试视频文件")
        return
    video_path = videos[0]
    print(f"  使用视频: {video_path.name} ({video_path.stat().st_size} 字节)")

    # 上传视频（不传 case_id，自动创建）
    with open(video_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/upload_video/",
            files={"file": (video_path.name, f, "video/mp4")},
            timeout=120
        )
    check(resp.status_code == 200, f"上传 API 返回 200 (实际 {resp.status_code})")

    data = resp.json()
    case_id = data.get("case_id")
    check(bool(case_id), f"返回 case_id: {case_id}")

    if not case_id:
        print(red("  ⚠ 无法继续测试 1，缺少 case_id"))
        return

    results["test1_case_id"] = case_id
    keyframes_count = len(data.get("keyframes", []))
    check(keyframes_count > 0, f"关键帧数量 > 0: 实际 {keyframes_count}")
    check("fused_evidence_packet" in data, "返回融合证据包")

    # 验证 case 已创建
    case_resp = api_get(f"/api/cases/{case_id}")
    check(case_resp.status_code == 200, f"GET /api/cases/{case_id} 返回 200")
    case_data = case_resp.json().get("data", {}) if case_resp.ok else {}
    check(case_data.get("id") == case_id, f"案件 ID 匹配: {case_data.get('id')}")
    check(case_data.get("status") == "待分析", f"案件状态 = 待分析: {case_data.get('status')}")
    check(bool(case_data.get("title")), f"案件标题非空: {case_data.get('title', '')[:40]}")

    # 验证证据列表
    ev_resp = api_get(f"/api/cases/{case_id}/evidences")
    check(ev_resp.status_code == 200, f"GET /api/cases/{case_id}/evidences 返回 200")
    ev_data = ev_resp.json().get("data", []) if ev_resp.ok else []

    # 分类证据
    video_evs = [e for e in ev_data if e.get("evidence_type") == "video"]
    keyframe_evs = [e for e in ev_data if e.get("evidence_type") == "keyframe"]
    check(len(video_evs) >= 1, f"视频证据记录 ≥ 1 条: 实际 {len(video_evs)}")
    check(len(keyframe_evs) >= 1, f"关键帧证据记录 ≥ 1 条: 实际 {len(keyframe_evs)}")

    if video_evs:
        ve = video_evs[0]
        check(bool(ve.get("file_path")), f"视频 file_path: {ve.get('file_path', '')[:50]}")
        check(bool(ve.get("file_name")), f"视频 file_name: {ve.get('file_name')}")
        check(ve.get("file_size", 0) > 0, f"视频 file_size > 0: {ve.get('file_size')}")
        check(ve.get("analysis_status") == "completed", f"视频 analysis_status = completed")
        meta = json.loads(ve.get("extra_data", "{}")) if isinstance(ve.get("extra_data"), str) else ve.get("extra_data", {})
        check(meta.get("accident_type", ""), f"元数据含 accident_type: {meta.get('accident_type')}")
        print(f"    视频元数据: vehicle_count={meta.get('vehicle_count')}, type_confidence={meta.get('type_confidence')}")

    if keyframe_evs:
        kf = keyframe_evs[0]
        check(bool(kf.get("file_path")), f"关键帧 file_path: {kf.get('file_path', '')[:50]}")
        check(kf.get("evidence_type") == "keyframe", f"关键帧类型 = keyframe")
        meta = json.loads(kf.get("extra_data", "{}")) if isinstance(kf.get("extra_data"), str) else kf.get("extra_data", {})
        check(meta.get("stage", ""), f"关键帧元数据含 stage: {meta.get('stage')}")
        check(isinstance(meta.get("time"), (int, float)), f"关键帧元数据含 time: {meta.get('time')}")

    # 验证融合证据包
    fused_resp = api_get(f"/api/cases/{case_id}/fused-evidence")
    check(fused_resp.status_code == 200, f"GET /api/cases/{case_id}/fused-evidence 返回 200")
    fused_data = fused_resp.json().get("data", {}) if fused_resp.ok else {}
    check(bool(fused_data.get("fused_evidence_packet")), "融合证据包非空")


# ── 测试 2: 手动创建案件 + 上传图片证据 + 验证 ──
def test_image_evidence():
    print(bold("\n── 测试 2: 手动创建案件 + 上传图片证据 ──"))

    case_id = f"TEST-IMG-{uuid.uuid4().hex[:8].upper()}"
    results["test2_case_id"] = case_id

    # 创建案件
    case_data = {
        "id": case_id,
        "title": "测试-图片证据",
        "accident_type": "追尾",
        "location": "测试路段",
        "status": "待分析",
        "description": "自动化测试图片上传",
        "priority": "中"
    }
    resp = requests.post(f"{BASE_URL}/api/cases", json=case_data, timeout=30)
    check(resp.status_code == 200, f"创建案件返回 200 (实际 {resp.status_code})")

    # 上传图片证据
    img_buf = make_test_image()
    resp = requests.post(
        f"{BASE_URL}/api/cases/{case_id}/evidences",
        json={
            "evidence_type": "image",
            "file_path": f"uploads/test/{case_id}/test_scene.jpg",
            "file_name": "test_scene.jpg",
            "file_size": img_buf.getbuffer().nbytes,
            "file_hash": "",
            "analysis_status": "completed",
            "related_stage": "image-analysis",
            "metadata": {"source": "automated_test", "scene": "test_intersection"}
        },
        timeout=30
    )
    check(resp.status_code == 200, f"上传图片证据返回 200 (实际 {resp.status_code})")

    # 验证证据列表
    ev_resp = api_get(f"/api/cases/{case_id}/evidences")
    check(ev_resp.status_code == 200, f"GET /api/cases/{case_id}/evidences 返回 200")
    ev_data = ev_resp.json().get("data", []) if ev_resp.ok else []
    img_evs = [e for e in ev_data if e.get("evidence_type") == "image"]
    check(len(img_evs) >= 1, f"图片证据记录 ≥ 1 条: 实际 {len(img_evs)}")

    if img_evs:
        ie = img_evs[0]
        check(ie.get("file_name") == "test_scene.jpg", f"图片 file_name = test_scene.jpg")
        check(ie.get("related_stage") == "image-analysis", f"图片 related_stage = image-analysis")
        meta = json.loads(ie.get("extra_data", "{}")) if isinstance(ie.get("extra_data"), str) else ie.get("extra_data", {})
        check(meta.get("source") == "automated_test", f"元数据 source = automated_test")


# ── 测试 3: 证明链 endpoint 一致性 ──
def test_evidence_chain_endpoints():
    print(bold("\n── 测试 3: 证据链 API 端点一致性 ──"))

    case_id = results.get("test1_case_id")
    if not case_id:
        fail("未找到测试 1 的 case_id，跳过")
        return

    endpoints = [
        ("GET", f"/api/cases/{case_id}"),
        ("GET", f"/api/cases/{case_id}/evidences"),
        ("GET", f"/api/cases/{case_id}/facts"),
        ("GET", f"/api/cases/{case_id}/matched-rules"),
        ("GET", f"/api/cases/{case_id}/reviews"),
        ("GET", f"/api/cases/{case_id}/liability-latest"),
        ("GET", f"/api/cases/{case_id}/fused-evidence"),
    ]
    for method, path in endpoints:
        resp = requests.request(method, f"{BASE_URL}{path}", timeout=30)
        check(resp.status_code in (200, 404, 401),
              f"{method} {path} → {resp.status_code} (成功/空数据/未认证均可)")


# ── 清理测试数据 ──
def cleanup():
    print(bold("\n── 清理测试数据 ──"))
    for key in ("test1_case_id", "test2_case_id"):
        case_id = results.get(key)
        if not case_id:
            continue
        try:
            resp = api_delete(f"/api/cases/{case_id}")
            if resp.status_code == 200:
                ok(f"已删除 {case_id}")
            else:
                fail(f"删除 {case_id} 失败: {resp.status_code}")
        except Exception as e:
            fail(f"删除 {case_id} 异常: {e}")


# ════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(bold("=" * 60))
    print(bold("  事故处理平台 — 上传链路自动化测试"))
    print(bold("=" * 60))
    print(f"  后端地址: {BASE_URL}")

    # 检查后端可用性
    try:
        h = api_get("/health")
        if h.ok:
            ok(f"后端 /health 可用: {h.json().get('status', 'unknown')}")
        else:
            fail(f"后端不可用: HTTP {h.status_code}")
            sys.exit(1)
    except Exception as e:
        fail(f"无法连接后端: {e}")
        sys.exit(1)

    try:
        test_video_upload()
        test_image_evidence()
        test_evidence_chain_endpoints()
    finally:
        cleanup()

    print(bold("\n" + "=" * 60))
    passed = results["pass"]
    failed = results["fail"]
    total = passed + failed
    print(f"  总计: {total} | {green(f'{passed} 通过')} | {red(f'{failed} 失败') if failed else ''}")
    print(bold("=" * 60))

    sys.exit(0 if failed == 0 else 1)
