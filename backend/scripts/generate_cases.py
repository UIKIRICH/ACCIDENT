"""
生成 400+ 事故案例数据，替换原 Excel 文件。
- 地区：延安市安塞区（约50%） / 济宁市曲阜市（约50%）
- 时间范围：2025-08-01 ~ 2026-03-31（均匀分布）
- 处理状态：全部"已完成"，最新 5 条为"待处理"
- submitted_at 列存储实际生成的时间
"""
import random
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

# ---- 城市 & 具体路段 ----
ANSAI_ROADS = [
    "包茂高速安塞出口匝道", "安塞区二道街与向阳路交叉口", "安塞区S206省道K45+200",
    "安塞区迎宾大道", "安塞区城南G210国道K780+100", "安塞区化子坪镇街道十字路口",
    "安塞区建华镇G65包茂高速入口", "安塞区真武洞镇环城路", "安塞区坪桥镇S303省道K88+500",
    "安塞区沿河湾镇工业园区路口", "安塞区马家沟T型路口", "安塞区高桥镇G210国道K795+300",
    "安塞区招安镇街道十字", "安塞区砖窑湾镇S206省道K52+800", "安塞区谭家营社区路口",
]
QUFU_ROADS = [
    "曲阜市春秋中路与大成路交叉口", "曲阜市G327国道K210+500", "曲阜市鼓楼大街与静轩路交叉口",
    "曲阜市孔子大道", "曲阜市小雪镇G104国道K560+300", "曲阜市鲁城街道逵泉路",
    "曲阜市时庄镇S335省道K120+800", "曲阜市陵城镇济微路", "曲阜市姚村镇G327国道K218+600",
    "曲阜市书院街道迎宾路", "曲阜市防山镇S244省道K78+200", "曲阜市息陬镇G104国道K568+900",
    "曲阜市王庄镇临庙路", "曲阜市吴村镇董庄路口", "曲阜市尼山镇圣水苑路口",
]

ACCIDENT_TYPES = {
    "追尾事故": ["后车未保持安全距离", "前车突然减速", "雨雾天气视距不足"],
    "变道事故": ["未打转向灯", "强行变道", "连续变道", "压实线变道"],
    "路口事故": ["闯红灯", "未让行", "转弯未让直行", "违反信号灯"],
    "倒车事故": ["倒车未观察", "停车场碰撞", "倒车速度过快"],
    "多车连环碰撞": ["视线受阻", "避让不及", "二次事故"],
    "侧向碰撞": ["侧方车辆强行并线", "路口转弯碰撞", "匝道汇入碰撞"],
    "行人事故": ["行人不走斑马线", "夜间行人横穿", "视线盲区"],
    "单车事故": ["避让障碍物", "爆胎失控", "路面湿滑", "疲劳驾驶"],
}

WEATHERS = ["晴", "多云", "阴", "小雨", "中雨", "雾", "霾", "雪", "大风"]
ROAD_ENVS = {
    "安塞区": [
        "高速公路，双向四车道", "省道三级公路，路面宽7米，夜间照明不足",
        "国道，双向两车道，弯道较多", "城市主干道，双向六车道，照明良好",
        "县道四级公路，路面宽6米", "山区公路，连续弯道", "镇区街道，人车混行",
    ],
    "曲阜市": [
        "城市主干道，双向六车道，照明良好", "国道，双向四车道，车流量大",
        "城市次干道，双向两车道，机非混行", "省道，双向两车道，夜间照明不足",
        "景区道路，路面宽8米，旅游车辆多", "镇区道路，人车混行，照明一般",
        "工业区道路，重型车辆多",
    ],
}

CAMERA_PERSPECTIVES = ["交通监控", "行车记录仪（前视）", "路侧摄像头", "交通执法仪", "无人机航拍"]
SYSTEM_ROUTES = ["yolo_primary", "qwen_fallback", "unanimous", "manual_review_required", "yolo_primary"]
SYSTEM_ROUTE_WEIGHTS = [35, 15, 30, 15, 5]

START_DATE = datetime(2025, 8, 1)
END_DATE = datetime(2026, 3, 31)


def generate_date(index: int, total: int) -> datetime:
    """在 2025-08-01 ~ 2026-03-31 范围内均匀分布日期"""
    total_days = (END_DATE - START_DATE).days
    day_offset = int((index / max(total - 1, 1)) * total_days)
    d = START_DATE + timedelta(days=day_offset)
    hour = random.randint(6, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return d.replace(hour=hour, minute=minute, second=second)


def generate_case(index: int, total: int, location_city: str, location_district: str, roads: list) -> dict:
    road = random.choice(roads)
    location = f"陕西省延安市{location_district}{road}" if location_district == "安塞区" else f"山东省济宁市曲阜市{road}"

    acc_type = random.choice(list(ACCIDENT_TYPES.keys()))
    acc_detail = random.choice(ACCIDENT_TYPES[acc_type])
    weather = random.choices(WEATHERS, weights=[15, 15, 10, 8, 6, 5, 5, 3, 3], k=1)[0]

    road_env_pool = ROAD_ENVS["安塞区"] if location_district == "安塞区" else ROAD_ENVS["曲阜市"]
    road_env = random.choice(road_env_pool)

    involved_count = random.choice([1, 2, 2, 2, 3, 3, 4, 5])
    injury_level = random.choice(["无人受伤", "1人轻伤", "1人轻伤", "2人轻伤", "1人重伤", "轻微刮擦无人伤"])

    vehicle_a = random.choice(["小轿车", "SUV", "面包车", "出租车", "公交车", "货车", "电动自行车", "摩托车"])
    vehicle_b = random.choice(["小轿车", "SUV", "面包车", "出租车", "货车", "电动自行车"]) if involved_count >= 2 else None

    plates_a = f"陕J·{random.choice('ABCDEFGH')}{random.randint(10000, 99999)}" if location_district == "安塞区" else f"鲁H·{random.choice('ABCDEFGH')}{random.randint(10000, 99999)}"
    plates_b = f"陕J·{random.choice('ABCDEFGH')}{random.randint(10000, 99999)}" if location_district == "安塞区" else f"鲁H·{random.choice('ABCDEFGH')}{random.randint(10000, 99999)}" if vehicle_b else ""

    case_date = generate_date(index, total)
    hour = case_date.hour
    time_desc = "上午" if hour < 12 else "下午" if hour < 18 else "夜间"

    desc_parts = []
    desc_parts.append(f"{time_desc}{hour}时许")
    desc_parts.append(f"在{location}")

    if acc_type == "追尾事故":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）因{acc_detail}")
        desc_parts.append(f"追尾前方{vehicle_b}（B车，{plates_b}），造成追尾事故")
    elif acc_type == "变道事故":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）在变道时{acc_detail}")
        desc_parts.append(f"与正常行驶的{vehicle_b}（B车，{plates_b}）发生碰撞")
    elif acc_type == "路口事故":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）通过路口时{acc_detail}")
        desc_parts.append(f"与{vehicle_b}（B车，{plates_b}）发生碰撞")
    elif acc_type == "倒车事故":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）{acc_detail}")
        desc_parts.append(f"撞到后方{vehicle_b}（B车，{plates_b}）")
    elif acc_type == "多车连环碰撞":
        desc_parts.append(f"因{acc_detail}")
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）首先与{vehicle_b}（B车，{plates_b}）发生碰撞")
        desc_parts.append(f"后方车辆避让不及，陆续发生追尾，形成多车连环碰撞事故")
    elif acc_type == "侧向碰撞":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）{acc_detail}")
        desc_parts.append(f"与{vehicle_b}（B车，{plates_b}）发生侧向碰撞事故")
    elif acc_type == "行人事故":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）行驶中因{acc_detail}")
        desc_parts.append("与横穿马路的行人发生碰撞")
    elif acc_type == "单车事故":
        desc_parts.append(f"{vehicle_a}（A车，{plates_a}）因{acc_detail}")
        desc_parts.append("导致车辆失控，发生单车事故")

    desc_parts.append(f"共涉及{involved_count}辆车，造成{injury_level}")
    description = "，".join(desc_parts) + "。"

    title = f"{location_district}{road} {acc_type}"

    route = random.choices(SYSTEM_ROUTES, weights=SYSTEM_ROUTE_WEIGHTS, k=1)[0]
    route_reasons = {
        "yolo_primary": "YOLO检测置信度高；证据充分",
        "qwen_fallback": "YOLO置信度不足；Qwen语义分析补充",
        "unanimous": "两模型结论一致；证据链完整",
        "manual_review_required": "模型结论冲突；证据不足；关键证据缺失",
    }
    route_reason = route_reasons.get(route, "证据需人工核验")

    yolo_conf = round(random.uniform(0.30, 0.98), 3)
    qwen_conf = round(random.uniform(0.30, 0.98), 3)

    video_avail = random.choice(["是", "是", "是", "否"])
    image_avail = random.choice(["是", "是", "否", "否"])
    text_avail = "是"
    keyframe_avail = random.choice(["是", "是", "否"])
    fact_avail = "是"

    completeness = 0
    if video_avail == "是": completeness += 25
    if image_avail == "是": completeness += 25
    if text_avail == "是": completeness += 25
    if keyframe_avail == "是": completeness += 15
    if fact_avail == "是": completeness += 10

    conflict_score = round(random.uniform(0, 0.8) if route == "manual_review_required" else random.uniform(0, 0.4), 3)

    yolo_candidate = random.choice([acc_type, acc_type, random.choice(list(ACCIDENT_TYPES.keys()))])
    qwen_candidate = random.choice([acc_type, acc_type, acc_type, acc_type, random.choice(list(ACCIDENT_TYPES.keys()))])
    conflict_detected = "是" if yolo_candidate != qwen_candidate or route == "manual_review_required" else "否"

    # 生成 case_id: ACC-YYYYMMDD-NNNN（日期 + 序号）
    date_str = case_date.strftime("%Y%m%d")
    seq = (index % 100) + 1
    case_id = f"ACC-{date_str}-{seq:04d}"

    return {
        "case_id": case_id,
        "title": title,
        "accident_type": acc_type,
        "location": location,
        "status": "已完成",
        "description": description,
        "weather": weather,
        "road_env": road_env,
        "submitted_at": case_date.strftime("%Y-%m-%d %H:%M:%S"),
        "Case Perspective": random.choice(CAMERA_PERSPECTIVES),
        "yolo_confidence": yolo_conf,
        "qwen_confidence": qwen_conf,
        "type_conflict_detected": conflict_detected,
        "estimated_involved_vehicle_count": involved_count,
        "evidence_completeness_score": completeness,
        "evidence_conflict_score": conflict_score,
        "video_available": video_avail,
        "image_available": image_avail,
        "text_available": text_avail,
        "keyframe_available": keyframe_avail,
        "structured_fact_available": fact_avail,
        "yolo_candidate_type": yolo_candidate,
        "qwen_candidate_type": qwen_candidate,
        "system_route": route,
        "route_reason": route_reason,
        "report_generated": random.choice(["是", "是", "是", "否"]),
        "human_review_decision": "",
        "system_liability_suggestion": "",
    }


def main():
    total = 420
    half = total // 2

    rows = []
    for i in range(half):
        rows.append(generate_case(i, total, "延安市", "安塞区", ANSAI_ROADS))
    for i in range(half, total):
        rows.append(generate_case(i, total, "济宁市", "曲阜市", QUFU_ROADS))

    # 按 submitted_at 排序
    rows.sort(key=lambda r: r["submitted_at"])

    # 设置处理状态：全部"已完成"，最新5条"待处理"
    for i, row in enumerate(rows):
        if i >= len(rows) - 5:
            row["status"] = "待处理"
        else:
            row["status"] = "已完成"

    df = pd.DataFrame(rows)
    output_path = Path(__file__).parent.parent.parent / "事故案例汇总表.xlsx"
    df.to_excel(str(output_path), index=False, engine="openpyxl")

    dates = [datetime.strptime(r["submitted_at"], "%Y-%m-%d %H:%M:%S") for r in rows]
    print(f"[DONE] Generated {len(rows)} cases -> {output_path}")
    print(f"  - 安塞区: {sum(1 for r in rows if '安塞区' in r['location'])}")
    print(f"  - 曲阜市: {sum(1 for r in rows if '曲阜市' in r['location'])}")
    print(f"  - 已完成: {sum(1 for r in rows if r['status'] == '已完成')}")
    print(f"  - 待处理: {sum(1 for r in rows if r['status'] == '待处理')}")
    print(f"  - 时间范围: {min(dates).strftime('%Y-%m-%d')} ~ {max(dates).strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    main()
