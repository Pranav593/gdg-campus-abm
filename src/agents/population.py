"""Build an enrollment-aware population from CourseBook and archetypes."""
import heapq
import json
import random
from collections import Counter

import campus_config as cfg

HARD_MAX_CREDITS = 19
TARGET_CREDITS = (10, 11, 12, 13, 14, 15, 16)
TARGET_WEIGHTS = (0.03, 0.07, 0.13, 0.28, 0.31, 0.14, 0.04)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def parse_floor(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 1


def infer_credits(course_number):
    """Use UTD's second-character credit convention; otherwise estimate 3."""
    value = str(course_number or "")
    if len(value) >= 2 and value[1].isdigit():
        return int(value[1]), "course_number"
    return 3, "estimated_fallback"


def allocate_counts(weights, n):
    raw = [w * n for w in weights]
    counts = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[: n - sum(counts)]:
        counts[i] += 1
    return counts


def load_section_pool(courses_path, graph_nodes):
    """Load sections with enrollment, weekday times, and routable buildings."""
    with open(courses_path) as f:
        raw = json.load(f)
    pool, skipped = {}, Counter()
    for s in raw:
        enrollment, capacity = s.get("enrollment"), s.get("capacity")
        if not isinstance(enrollment, int) or not isinstance(capacity, int):
            skipped["invalid_enrollment"] += 1
            continue
        meetings, ok = [], True
        for m in s.get("meetings", []):
            if m.get("day") not in cfg.DAYS:
                continue
            if not m.get("start_time") or not m.get("end_time"):
                skipped["missing_time"] += 1
                ok = False
                break
            if m.get("building") not in graph_nodes:
                skipped["unmapped_building"] += 1
                ok = False
                break
            meetings.append({
                "section_id": s["section_id"], "day": m["day"],
                "start_time": m["start_time"], "end_time": m["end_time"],
                "building": m["building"], "floor": parse_floor(m.get("floor")),
                "room": str(m.get("room", "")),
                "start_s": cfg.to_seconds(m["start_time"]), "end_s": cfg.to_seconds(m["end_time"]),
            })
        if not ok:
            continue
        if not meetings:
            skipped["no_weekday_meetings"] += 1
            continue
        credits, credit_source = s.get("credits"), s.get("credit_source")
        if not isinstance(credits, int):
            credits, credit_source = infer_credits(s.get("course_number"))
        current, maximum = max(0, enrollment), max(0, capacity)
        section = {
            "section_id": s["section_id"], "course_key": (s["prefix"], s["course_number"]),
            "course": f"{s['prefix']} {s['course_number']}", "credits": credits,
            "credit_source": credit_source, "source_enrollment": current,
            "max_enrollment": maximum, "target_enrollment": min(current, maximum),
            "meetings": meetings,
        }
        pool.setdefault(section["course_key"], []).append(section)
    sections = [s for values in pool.values() for s in values]
    stats = {
        "processed_sections": len(raw),
        "processed_unique_courses": len({(s.get("prefix"), s.get("course_number")) for s in raw}),
        "processed_valid_enrollment_sections": sum(isinstance(s.get("enrollment"), int)
                                                     and isinstance(s.get("capacity"), int) for s in raw),
        "processed_source_enrollment": sum(s.get("enrollment", 0) for s in raw if isinstance(s.get("enrollment"), int)),
        "processed_max_enrollment": sum(s.get("capacity", 0) for s in raw if isinstance(s.get("capacity"), int)),
        "processed_duplicate_section_ids": len(raw) - len({s.get("section_id") for s in raw}),
        "processed_duplicate_class_numbers": len(raw) - len({s.get("class_number") for s in raw}),
        "usable_sections": len(sections), "usable_unique_courses": len(pool),
        "usable_source_enrollment": sum(s["source_enrollment"] for s in sections),
        "usable_target_enrollment": sum(s["target_enrollment"] for s in sections),
        "source_over_max_sections": sum(s["source_enrollment"] > s["max_enrollment"] for s in sections),
        "source_over_max_excess": sum(max(0, s["source_enrollment"] - s["max_enrollment"])
                                      for s in sections),
        "credit_sources": dict(Counter(s["credit_source"] for s in sections)),
        "skipped": dict(skipped),
    }
    print(f"section pool: {stats['usable_unique_courses']} courses / {stats['usable_sections']} sections usable; "
          f"{sum(skipped.values())} skipped")
    return pool, stats


def _overlaps(a, b):
    return a["day"] == b["day"] and a["start_s"] < b["end_s"] and b["start_s"] < a["end_s"]


def _eligible(agent, section, credit_limit=None):
    limit = min(HARD_MAX_CREDITS, agent["target_credits"]) if credit_limit is None else credit_limit
    if agent["credits"] + section["credits"] > limit:
        return False
    if section["course_key"] in agent["course_keys"]:
        return False
    return not any(_overlaps(m, x) for m in section["meetings"] for x in agent["schedule"])


def _assign_enrollment(agents, sections, scale, rng):
    """Assign section targets. A final token handles odd/remainder enrollment."""
    rng.shuffle(sections)
    heap = [(0.0, rng.random(), i) for i in range(len(agents))]
    heapq.heapify(heap)
    assigned, unfilled, pending = Counter(), Counter(), []
    for section in sections:
        target = section["target_enrollment"]
        tokens = [scale] * (target // scale)
        if target % scale:
            tokens.append(target % scale)
        for represented in tokens:
            held, chosen = [], None
            for _ in range(min(len(agents), 80)):
                item = heapq.heappop(heap)
                if _eligible(agents[item[2]], section):
                    chosen = item[2]
                    break
                held.append(item)
            for item in held:
                heapq.heappush(heap, item)
            if chosen is None:
                unfilled[section["section_id"]] += represented
                pending.append((section, represented))
                continue
            agent = agents[chosen]
            for meeting in section["meetings"]:
                agent["schedule"].append(dict(meeting, credits=section["credits"],
                                              represented_enrollment=represented))
            agent["course_keys"].add(section["course_key"])
            agent["section_ids"].add(section["section_id"])
            agent["credits"] += section["credits"]
            assigned[section["section_id"]] += represented
            priority = agent["credits"] / max(1, agent["target_credits"])
            heapq.heappush(heap, (priority, rng.random(), chosen))
    # Reconcile residual slots against a 14-credit ceiling. This improves source
    # matching without using the 19-credit hard maximum as the normal target.
    heap = [(a["credits"], rng.random(), i) for i, a in enumerate(agents)]
    heapq.heapify(heap)
    for section, represented in pending:
        held, chosen = [], None
        for _ in range(min(len(agents), 120)):
            item = heapq.heappop(heap)
            if _eligible(agents[item[2]], section, credit_limit=14):
                chosen = item[2]
                break
            held.append(item)
        for item in held:
            heapq.heappush(heap, item)
        if chosen is None:
            continue
        agent = agents[chosen]
        for meeting in section["meetings"]:
            agent["schedule"].append(dict(meeting, credits=section["credits"],
                                          represented_enrollment=represented))
        agent["course_keys"].add(section["course_key"])
        agent["section_ids"].add(section["section_id"])
        agent["credits"] += section["credits"]
        assigned[section["section_id"]] += represented
        unfilled[section["section_id"]] -= represented
        heapq.heappush(heap, (agent["credits"], rng.random(), chosen))
    return assigned, unfilled


def make_population(archetypes, n, pool, rng, scale_ratio=1, pool_stats=None, return_report=False):
    counts = allocate_counts([a["population_weight"] for a in archetypes], n)
    permits, permit_weights = zip(*cfg.PERMIT_DISTRIBUTION.items())
    agents, next_id = [], 1
    for arche, count in zip(archetypes, counts):
        for _ in range(count):
            traits = {}
            for key, value in arche["traits"].items():
                if key == "walking_speed_mps":
                    traits[key] = clamp(rng.gauss(value, cfg.WALK_STD), 0.8, 1.8)
                else:
                    traits[key] = clamp(rng.gauss(value, cfg.TRAIT_STD), 0.0, 1.0)
            state = dict(arche["state"])
            state["hunger"] = clamp(rng.gauss(state["hunger"], 0.08), 0, 1)
            state["energy"] = clamp(rng.gauss(state["energy"], 0.08), 0, 1)
            agents.append({
                "agent_id": next_id, "archetype_tag": arche["archetype_tag"],
                "commuter_tag": {"type": arche["commuter_tag"]["type"],
                                 "parking_permit": rng.choices(permits, permit_weights)[0]},
                "parks_near_first": rng.random() < 0.5, "traits": traits, "state": state,
                "schedule": [], "credits": 0,
                "target_credits": rng.choices(TARGET_CREDITS, TARGET_WEIGHTS)[0],
                "course_keys": set(), "section_ids": set(),
            })
            next_id += 1
    sections = [s for choices in pool.values() for s in choices]
    assigned, _ = _assign_enrollment(agents, sections, max(1, int(scale_ratio)), rng)
    section_rows = []
    for section in sorted(sections, key=lambda s: s["section_id"]):
        value = assigned[section["section_id"]]
        section_rows.append({
            "section_id": section["section_id"], "course": section["course"],
            "credits": section["credits"], "credit_source": section["credit_source"],
            "source_enrollment": section["source_enrollment"], "max_enrollment": section["max_enrollment"],
            "target_enrollment": section["target_enrollment"], "assigned_enrollment": value,
            "unfilled_enrollment": section["target_enrollment"] - value,
            "over_capacity": value > section["max_enrollment"],
        })
    credit_counts = Counter(a["credits"] for a in agents)
    exact = sum(r["assigned_enrollment"] == r["target_enrollment"] for r in section_rows)
    report = {
        "coursebook": pool_stats or {}, "population": n, "scale_ratio": scale_ratio,
        "source_enrollment_usable": sum(r["source_enrollment"] for r in section_rows),
        "target_enrollment_usable": sum(r["target_enrollment"] for r in section_rows),
        "assigned_enrollment": sum(r["assigned_enrollment"] for r in section_rows),
        "unfilled_enrollment": sum(r["unfilled_enrollment"] for r in section_rows),
        "sections_exact": exact, "sections_total": len(section_rows),
        "sections_exact_percent": 100 * exact / max(1, len(section_rows)),
        "over_capacity_sections": sum(r["over_capacity"] for r in section_rows),
        "conflicting_agents": sum(any(_overlaps(m, x) for i, m in enumerate(a["schedule"])
                                      for x in a["schedule"][i + 1:] if m["section_id"] != x["section_id"])
                                  for a in agents),
        "duplicate_course_agents": sum(len(a["course_keys"]) != len(a["section_ids"]) for a in agents),
        "credit_hour_distribution": {str(k): credit_counts[k] for k in sorted(credit_counts)},
        "agents_13_14_credits": credit_counts[13] + credit_counts[14],
        "agents_13_14_percent": 100 * (credit_counts[13] + credit_counts[14]) / max(1, n),
        "agents_over_19_credits": sum(v for k, v in credit_counts.items() if k > HARD_MAX_CREDITS),
        "empty_schedules": credit_counts[0],
        "unusually_light_schedules_under_9": sum(v for k, v in credit_counts.items() if k < 9),
        "odd_remainder_strategy": "one agent represents the target remainder for that section only",
        "sections": section_rows,
    }
    for agent in agents:
        agent["schedule"].sort(key=lambda m: (cfg.DAYS.index(m["day"]), m["start_s"], m["section_id"]))
        del agent["course_keys"]
        del agent["section_ids"]
    return (agents, report) if return_report else agents


def strip_for_json(agents):
    out = []
    for agent in agents:
        item = {k: v for k, v in agent.items() if k != "target_credits"}
        item["schedule"] = [{k: m[k] for k in ("section_id", "day", "start_time", "end_time",
                                                 "building", "floor", "room", "credits",
                                                 "represented_enrollment")} for m in agent["schedule"]]
        out.append(item)
    return out
