"""Builds the individual agent population from archetypes.json + CourseBook sections.
Traits get bell-curve variation once, at creation, then stay fixed."""
import json
import random

import campus_config as cfg


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def parse_floor(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 1


def allocate_counts(weights, n):
    """Largest-remainder allocation so counts sum to exactly n."""
    raw = [w * n for w in weights]
    counts = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[: n - sum(counts)]:
        counts[i] += 1
    return counts


def load_section_pool(courses_path, graph_nodes):
    """{(prefix, number): [section, ...]}; keeps only sections with Mon-Fri meetings whose
    buildings are all graph nodes. Each section: {section_id, meetings:[...]}."""
    with open(courses_path) as f:
        raw = json.load(f)
    pool, skipped = {}, 0
    for s in raw:
        meetings = []
        ok = True
        for m in s.get("meetings", []):
            if m.get("day") not in cfg.DAYS:
                continue
            if m.get("building") not in graph_nodes or not m.get("start_time") or not m.get("end_time"):
                ok = False
                break
            meetings.append({
                "section_id": s["section_id"], "day": m["day"],
                "start_time": m["start_time"], "end_time": m["end_time"],
                "building": m["building"], "floor": parse_floor(m.get("floor")),
                "room": str(m.get("room", "")),
                "start_s": cfg.to_seconds(m["start_time"]), "end_s": cfg.to_seconds(m["end_time"]),
            })
        if not ok or not meetings:
            skipped += 1
            continue
        pool.setdefault((s["prefix"], s["course_number"]), []).append(
            {"section_id": s["section_id"], "meetings": meetings})
    print(f"section pool: {len(pool)} courses usable, {skipped} sections skipped "
          f"(online/TBA/building not in graph)")
    return pool


def _overlaps(a, b):
    return a["day"] == b["day"] and a["start_s"] < b["end_s"] and b["start_s"] < a["end_s"]


def pick_schedule(pool, keys, rng):
    load = rng.choices([2, 3, 4, 5, 6], [0.05, 0.20, 0.35, 0.30, 0.10])[0]
    chosen, meetings = [], []
    for key in rng.sample(keys, min(len(keys), load * 4)):
        if len(chosen) >= load:
            break
        sec = rng.choice(pool[key])
        if any(_overlaps(m, x) for m in sec["meetings"] for x in meetings):
            continue
        chosen.append(sec["section_id"])
        meetings.extend(sec["meetings"])
    return meetings


def make_population(archetypes, n, pool, rng):
    keys = list(pool)
    counts = allocate_counts([a["population_weight"] for a in archetypes], n)
    permits, pw = zip(*cfg.PERMIT_DISTRIBUTION.items())
    agents, next_id = [], 1
    for arche, count in zip(archetypes, counts):
        base = arche["traits"]
        for _ in range(count):
            traits = {}
            for k, v in base.items():
                if k == "walking_speed_mps":
                    traits[k] = clamp(rng.gauss(v, cfg.WALK_STD), 0.8, 1.8)
                else:
                    traits[k] = clamp(rng.gauss(v, cfg.TRAIT_STD), 0.0, 1.0)
            st = dict(arche["state"])
            st["hunger"] = clamp(rng.gauss(st["hunger"], 0.08), 0, 1)
            st["energy"] = clamp(rng.gauss(st["energy"], 0.08), 0, 1)
            agents.append({
                "agent_id": next_id,
                "archetype_tag": arche["archetype_tag"],
                "commuter_tag": {"type": arche["commuter_tag"]["type"],
                                 "parking_permit": rng.choices(permits, pw)[0]},
                "parks_near_first": rng.random() < 0.5,
                "traits": traits,
                "state": st,
                "schedule": pick_schedule(pool, keys, rng),
            })
            next_id += 1
    return agents


def strip_for_json(agents):
    out = []
    for a in agents:
        b = dict(a)
        b["schedule"] = [{k: m[k] for k in ("section_id", "day", "start_time", "end_time",
                                              "building", "floor", "room")} for m in a["schedule"]]
        out.append(b)
    return out
