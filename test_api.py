"""
API 测试脚本 - 依次测试所有核心接口
"""
import subprocess
import sys
import time
import json

# 确保 requests 可用
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE = "http://127.0.0.1:8000"
HEADERS = {}
CASE_ID = None
TASK_ID = None
TOKEN = None

passed = 0
failed = 0
errors = []

def test(name, method, url, expected_status=None, json_data=None, expect_keys=None):
    global passed, failed, errors, HEADERS, CASE_ID, TASK_ID, TOKEN
    try:
        r = getattr(requests, method)(f"{BASE}{url}", headers=HEADERS, json=json_data, timeout=5)
        ok = True
        reason = ""

        if expected_status and r.status_code != expected_status:
            ok = False
            reason = f"Expected {expected_status}, got {r.status_code}: {r.text[:300]}"

        if ok and expect_keys:
            body = r.json() if r.status_code != 204 else {}
            for key in expect_keys:
                if key not in body:
                    ok = False
                    reason = f"Missing key '{key}' in response: {r.text[:300]}"
                    break

        if ok:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            msg = f"  [FAIL] {name}: {reason}"
            print(msg)
            errors.append(msg)

        return r
    except Exception as e:
        failed += 1
        msg = f"  [FAIL] {name}: {e}"
        print(msg)
        errors.append(msg)
        return None

print("="*50)
print("Running API tests against", BASE)
print("="*50)

# a. 登录
r = test("POST /api/auth/login", "post", "/api/auth/login", 200,
         json_data={"username": "admin", "password": "admin123"}, expect_keys=["success", "data"])
if r:
    body = r.json()
    TOKEN = body.get("data", {}).get("token", "")
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

# b. 删除规则 R-001（需要 admin）
r = test("DELETE /api/rules/R-001", "delete", "/api/rules/R-001", 200)

# c. 创建案件
r = test("POST /api/cases", "post", "/api/cases", 200,
         json_data={"title": "API测试案件", "accident_type": "追尾事故", "priority": "高"})
if r:
    body = r.json()
    CASE_ID = body.get("data", {}).get("id", "")
    print(f"      → case_id = {CASE_ID}")

# d. 非法状态流转（草稿 → 已完成 不合法）
r = test("PUT /api/cases/{id}/status (illegal)", "put",
         f"/api/cases/{CASE_ID}/status", 400,
         json_data={"status": "已完成"})

# e. 合法状态流转（草稿 → 待分析）
r = test("PUT /api/cases/{id}/status (legal)", "put",
         f"/api/cases/{CASE_ID}/status", 200,
         json_data={"status": "待分析"})

# f. 添加证据
r = test("POST /api/cases/{id}/evidences", "post",
         f"/api/cases/{CASE_ID}/evidences", 200,
         json_data={"evidence_type": "image", "file_path": "/tmp/test.jpg"})

# g. 查询证据列表
r = test("GET /api/cases/{id}/evidences", "get",
         f"/api/cases/{CASE_ID}/evidences", 200)

# h. 创建分析任务
r = test("POST /api/tasks/analysis", "post",
         "/api/tasks/analysis", 200,
         json_data={"case_id": CASE_ID, "task_type": "image"})
if r:
    body = r.json()
    TASK_ID = body.get("data", {}).get("task_id", "")
    print(f"      → task_id = {TASK_ID}")

# i. 查询任务状态
r = test("GET /api/tasks/{id}/status", "get",
         f"/api/tasks/{TASK_ID}/status", 200)

# j. 更新任务状态
r = test("PUT /api/tasks/{id}/status", "put",
         f"/api/tasks/{TASK_ID}/status", 200,
         json_data={"task_status": "running", "progress": 50})

# k. 保存责任判定（含版本）
r = test("POST /api/cases/{id}/liability-v2", "post",
         f"/api/cases/{CASE_ID}/liability-v2", 200,
         json_data={"summary": "测试结论", "ratio": "7:3", "hit_rules": []})

# l. 查询责任版本列表
r = test("GET /api/cases/{id}/liability-versions", "get",
         f"/api/cases/{CASE_ID}/liability-versions", 200)

# m. 创建结构化事实
r = test("POST /api/cases/{id}/facts", "post",
         f"/api/cases/{CASE_ID}/facts", 200,
         json_data={"source_type": "video", "fact_type": "vehicle_count", "fact_value": "2", "confidence": 0.9})

# n. 证据一致性检测
r = test("GET /api/cases/{id}/evidence-consistency", "get",
         f"/api/cases/{CASE_ID}/evidence-consistency", 200)

# o. 健康检查
r = test("GET /health", "get", "/health", 200)

# p. 创建第二个规则并删除（验证 admin 权限工作）
# (R-001 was already deleted; just test POST + DELETE with the next available id)
r = test("POST /api/rules (create new)", "post", "/api/rules", 200,
         json_data={"name": "测试规则", "type": "测试"})
new_rule_id = None
if r:
    body = r.json()
    new_rule_id = body.get("data", {}).get("id", "")
if new_rule_id:
    r = test("DELETE /api/rules/{new_id}", "delete", f"/api/rules/{new_rule_id}", 200)

# Cleanup: delete the test case
test("DELETE /api/cases/{id} (cleanup)", "delete", f"/api/cases/{CASE_ID}", 200)

print("\n" + "="*50)
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
print("="*50)

if errors:
    print("\nFailed tests:")
    for e in errors:
        print(e)

if failed > 0:
    print("\nSOME TESTS FAILED")
    sys.exit(1)
else:
    print("\nALL TESTS PASSED")
    sys.exit(0)
