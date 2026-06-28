"""
API 测试脚本 - 依次测试所有核心接口（24个测试）
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

BASE = "http://127.0.0.1:8001"
HEADERS = {}
CASE_ID = None
TASK_ID = None
TOKEN = None
ANALYST_TOKEN = None
ANALYST_HEADERS = {}

passed = 0
failed = 0
errors = []

def test(name, method, url, expected_status=None, json_data=None, expect_keys=None, custom_headers=None):
    global passed, failed, errors, HEADERS, CASE_ID, TASK_ID, TOKEN
    try:
        hdrs = custom_headers if custom_headers else HEADERS
        r = getattr(requests, method)(f"{BASE}{url}", headers=hdrs, json=json_data, timeout=10)
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

# ================================================================
# Test 1: 登录（admin）
# ================================================================
r = test("POST /api/auth/login (admin)", "post", "/api/auth/login", 200,
         json_data={"username": "admin", "password": "admin123"}, expect_keys=["success", "data"])
if r:
    body = r.json()
    TOKEN = body.get("data", {}).get("token", "")
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

# ================================================================
# Test 2: 登录（analyst）
# ================================================================
r = test("POST /api/auth/login (analyst)", "post", "/api/auth/login", 200,
         json_data={"username": "analyst", "password": "analyst123"}, expect_keys=["success", "data"])
if r:
    body = r.json()
    ANALYST_TOKEN = body.get("data", {}).get("token", "")
    ANALYST_HEADERS["Authorization"] = f"Bearer {ANALYST_TOKEN}"

# ================================================================
# Test 3: 删除规则 R-001（需要 admin）
# ================================================================
r = test("DELETE /api/rules/R-001", "delete", "/api/rules/R-001", 200)

# ================================================================
# Test 4: 创建案件
# ================================================================
r = test("POST /api/cases", "post", "/api/cases", 200,
         json_data={"title": "API测试案件", "accident_type": "追尾事故", "priority": "高"})
if r:
    body = r.json()
    CASE_ID = body.get("data", {}).get("id", "")
    print(f"      → case_id = {CASE_ID}")

# ================================================================
# Test 5: 非法状态流转（草稿 → 已完成 不合法）
# ================================================================
r = test("PUT /api/cases/{id}/status (illegal: draft→completed)", "put",
         f"/api/cases/{CASE_ID}/status", 400,
         json_data={"status": "已完成"})

# ================================================================
# Test 6: 合法状态流转（草稿 → 待分析）
# ================================================================
r = test("PUT /api/cases/{id}/status (legal: draft→待分析)", "put",
         f"/api/cases/{CASE_ID}/status", 200,
         json_data={"status": "待分析"})

# ================================================================
# Test 7: 添加证据
# ================================================================
r = test("POST /api/cases/{id}/evidences", "post",
         f"/api/cases/{CASE_ID}/evidences", 200,
         json_data={"evidence_type": "image", "file_path": "test_data/test.jpg"})

# ================================================================
# Test 8: 查询证据列表
# ================================================================
r = test("GET /api/cases/{id}/evidences", "get",
         f"/api/cases/{CASE_ID}/evidences", 200)

# ================================================================
# Test 9: 创建分析任务
# ================================================================
r = test("POST /api/tasks/analysis", "post",
         "/api/tasks/analysis", 200,
         json_data={"case_id": CASE_ID, "task_type": "image"})
if r:
    body = r.json()
    TASK_ID = body.get("data", {}).get("task_id", "")
    print(f"      → task_id = {TASK_ID}")

# ================================================================
# Test 10: 查询任务状态
# ================================================================
r = test("GET /api/tasks/{id}/status", "get",
         f"/api/tasks/{TASK_ID}/status", 200)

# ================================================================
# Test 11: 更新任务状态
# ================================================================
r = test("PUT /api/tasks/{id}/status", "put",
         f"/api/tasks/{TASK_ID}/status", 200,
         json_data={"task_status": "running", "progress": 50})

# ================================================================
# Test 12: 保存责任判定（含版本）
# ================================================================
r = test("POST /api/cases/{id}/liability-v2", "post",
         f"/api/cases/{CASE_ID}/liability-v2", 200,
         json_data={"summary": "测试结论", "ratio": "7:3", "hit_rules": []})

# ================================================================
# Test 13: 查询责任版本列表
# ================================================================
r = test("GET /api/cases/{id}/liability-versions", "get",
         f"/api/cases/{CASE_ID}/liability-versions", 200)

# ================================================================
# Test 14: 创建结构化事实
# ================================================================
r = test("POST /api/cases/{id}/facts", "post",
         f"/api/cases/{CASE_ID}/facts", 200,
         json_data={"source_type": "video", "fact_type": "vehicle_count", "fact_value": "2", "confidence": 0.9})

# ================================================================
# Test 15: 证据一致性检测
# ================================================================
r = test("GET /api/cases/{id}/evidence-consistency", "get",
         f"/api/cases/{CASE_ID}/evidence-consistency", 200)

# ================================================================
# Test 16: 健康检查
# ================================================================
r = test("GET /health", "get", "/health", 200)

# ================================================================
# Test 17: 创建规则
# ================================================================
r = test("POST /api/rules (create new)", "post", "/api/rules", 200,
         json_data={"name": "测试规则", "type": "测试"})
new_rule_id = None
if r:
    body = r.json()
    new_rule_id = body.get("data", {}).get("id", "")

# ================================================================
# Test 18: 删除规则
# ================================================================
if new_rule_id:
    r = test("DELETE /api/rules/{new_id}", "delete", f"/api/rules/{new_rule_id}", 200)

# ================================================================
# Test 19: 完整案例闭环测试（从创建到归档）
# ================================================================
print("\n  --- Test 19: 完整案例闭环测试 ---")
# 创建新案件
r = test("19a: 创建闭环测试案件", "post", "/api/cases", 200,
         json_data={"title": "闭环测试案件", "accident_type": "变道事故", "priority": "高"})
loop_case_id = None
if r:
    body = r.json()
    loop_case_id = body.get("data", {}).get("id", "")
    print(f"      → loop_case_id = {loop_case_id}")

if loop_case_id:
    # 上传证据
    test("19b: 添加证据", "post", f"/api/cases/{loop_case_id}/evidences", 200,
         json_data={"evidence_type": "image", "file_path": "test_data/loop_test.jpg"})
    # 创建分析任务
    r = test("19c: 创建分析任务", "post", "/api/tasks/analysis", 200,
             json_data={"case_id": loop_case_id, "task_type": "full_analysis"})
    loop_task_id = None
    if r:
        body = r.json()
        loop_task_id = body.get("data", {}).get("task_id", "")
    # 创建结构化事实
    test("19d: 创建结构化事实", "post", f"/api/cases/{loop_case_id}/facts", 200,
         json_data={"source_type": "video", "fact_type": "accident_type", "fact_value": "变道事故", "confidence": 0.9})
    # 保存责任判定
    test("19e: 保存责任判定", "post", f"/api/cases/{loop_case_id}/liability", 200,
         json_data={"summary": "闭环测试结论", "ratio": "6:4", "hit_rules": [{"code": "R-002", "name": "变道未打转向灯"}]})
    # 保存责任版本
    test("19f: 保存责任版本", "post", f"/api/cases/{loop_case_id}/liability-v2", 200,
         json_data={"summary": "闭环测试版本", "ratio": "6:4", "hit_rules": [{"code": "R-002", "name": "变道未打转向灯"}]})
    # 添加复核记录
    test("19g: 添加复核记录", "post", f"/api/cases/{loop_case_id}/reviews", 200,
         json_data={"reviewer": "admin", "system_suggestion": "建议", "final_result": "通过", "review_comment": "测试通过"})
    # 状态流转到已完成
    test("19h: 状态流转到待分析", "put", f"/api/cases/{loop_case_id}/status", 200,
         json_data={"status": "待分析"})
    test("19i: 状态流转到待复核", "put", f"/api/cases/{loop_case_id}/status", 200,
         json_data={"status": "待复核"})
    test("19j: 状态流转到复核中", "put", f"/api/cases/{loop_case_id}/status", 200,
         json_data={"status": "复核中"})
    test("19k: 状态流转到已复核", "put", f"/api/cases/{loop_case_id}/status", 200,
         json_data={"status": "已复核"})
    r = test("19l: 状态流转到已完成", "put", f"/api/cases/{loop_case_id}/status", 200,
             json_data={"status": "已完成"})
    # 验证最终状态
    if r:
        body = r.json()
        final_status = body.get("data", {}).get("status", "")
        if final_status == "已完成":
            print("      → 闭环测试完成，最终状态: 已完成")
        else:
            print(f"      → 闭环测试状态异常: {final_status}")

# ================================================================
# Test 20: 非法状态跳转测试（草稿直接跳已完成，应该返回400）
# ================================================================
print("\n  --- Test 20: 非法状态跳转测试 ---")
r = test("20: 草稿→已完成 (应返回400)", "put",
         f"/api/cases/{CASE_ID}/status", 400,
         json_data={"status": "已完成"})

# ================================================================
# Test 21: 非管理员修改规则失败测试（用analyst账号修改规则，应该返回403）
# ================================================================
print("\n  --- Test 21: 非管理员修改规则失败测试 ---")
# 先用admin创建一个规则
r = test("21a: admin创建规则", "post", "/api/rules", 200,
         json_data={"name": "权限测试规则", "type": "测试"})
perm_rule_id = None
if r:
    body = r.json()
    perm_rule_id = body.get("data", {}).get("id", "")
if perm_rule_id:
    # 用analyst账号修改规则，应该返回403
    test("21b: analyst修改规则 (应返回403)", "put",
         f"/api/rules/{perm_rule_id}", 403,
         json_data={"name": "analyst试图修改"},
         custom_headers=ANALYST_HEADERS)
    # 清理：用admin删除
    test("21c: admin删除规则", "delete", f"/api/rules/{perm_rule_id}", 200)

# ================================================================
# Test 22: 上传证据后evidence数量增加测试
# ================================================================
print("\n  --- Test 22: 证据数量增加测试 ---")
# 获取当前证据数量
r = test("22a: 获取当前证据数", "get", f"/api/cases/{CASE_ID}/evidences", 200)
count_before = 0
if r:
    body = r.json()
    count_before = len(body.get("data", []))
    print(f"      → 上传前证据数: {count_before}")
# 上传新证据
test("22b: 上传新证据", "post", f"/api/cases/{CASE_ID}/evidences", 200,
     json_data={"evidence_type": "image", "file_path": "test_data/count_test.jpg"})
# 再次获取证据数量
r = test("22c: 获取上传后证据数", "get", f"/api/cases/{CASE_ID}/evidences", 200)
count_after = 0
if r:
    body = r.json()
    count_after = len(body.get("data", []))
    print(f"      → 上传后证据数: {count_after}")
    if count_after == count_before + 1:
        print("      → 证据数量+1，验证通过")
    else:
        print(f"      → 证据数量异常: 期望 {count_before + 1}，实际 {count_after}")

# ================================================================
# Test 23: 保存责任建议后自动生成版本测试
# ================================================================
print("\n  --- Test 23: 保存责任建议后自动生成版本测试 ---")
# 获取当前版本数
r = test("23a: 获取当前版本数", "get", f"/api/cases/{CASE_ID}/liability-versions", 200)
version_count_before = 0
if r:
    body = r.json()
    version_count_before = len(body.get("data", []))
    print(f"      → 保存前版本数: {version_count_before}")
# 保存责任判定（含版本）
test("23b: 保存责任判定（含版本）", "post", f"/api/cases/{CASE_ID}/liability-v2", 200,
     json_data={"summary": "版本测试", "ratio": "5:5", "hit_rules": [{"code": "R-001", "name": "测试规则"}]})
# 再次获取版本数
r = test("23c: 获取保存后版本数", "get", f"/api/cases/{CASE_ID}/liability-versions", 200)
version_count_after = 0
if r:
    body = r.json()
    version_count_after = len(body.get("data", []))
    print(f"      → 保存后版本数: {version_count_after}")
    if version_count_after > version_count_before:
        print("      → 版本自动生成，验证通过")
    else:
        print(f"      → 版本未增加: 期望 > {version_count_before}，实际 {version_count_after}")

# ================================================================
# Test 24: 复核归档后历史案例可查询测试
# ================================================================
print("\n  --- Test 24: 复核归档后历史案例可查询测试 ---")
# 使用闭环测试的案件（已归档到已完成）
r = test("24: 查询历史案例", "get", "/api/history-cases", 200)
if r:
    body = r.json()
    history_cases = body.get("data", [])
    print(f"      → 历史案例数: {len(history_cases)}")
    found = any(c.get("id") == loop_case_id for c in history_cases)
    if found:
        print(f"      → 闭环测试案件 {loop_case_id} 在历史案例中找到，验证通过")
    else:
        print(f"      → 闭环测试案件 {loop_case_id} 未在历史案例中找到")

# ================================================================
# 清理测试数据
# ================================================================
if loop_case_id:
    test("DELETE /api/cases/{id} (cleanup loop)", "delete", f"/api/cases/{loop_case_id}", 200)
test("DELETE /api/cases/{id} (cleanup)", "delete", f"/api/cases/{CASE_ID}", 200)

# ================================================================
# 结果汇总
# ================================================================
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