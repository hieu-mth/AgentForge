"""AI chooses only from Owner-enabled, policy-compatible methods. No inference dispatch here."""

MIN_CLOUD_SECONDS = 12
MAX_CLOUD_SECONDS = 240


def choose(brief, candidates, infer):
    if not candidates:
        raise ValueError("No permitted production routes.")
    options = {f"{item['method']}:{item['id']}": item for item in candidates}
    if len(options) == 1:
        key = next(iter(options))
        reason = "Chỉ có một tuyến tương thích quyền, ngân sách và model đã đăng ký."
    else:
        schema = {"type": "object", "additionalProperties": False, "required": ["choice", "reason"],
                  "properties": {"choice": {"type": "string", "enum": list(options)},
                                 "reason": {"type": "string", "minLength": 1, "maxLength": 350}}}
        answer = infer("Choose one permitted production route, prioritizing local unless the script needs longer "
                       "continuous motion, native audio or lower GPU load. Never assume an unverified provider is better. "
                       "Hybrid uses a local reference image for each shot; cloud generates from prompt and may use the "
                       "previous actual frame for continuity. Cloud bills at least 6 seconds per shot. "
                       "Choose based on narrative, reference consistency and explicit seconds cap. "
                       "execution_ready is configuration admission only, not a quality benchmark. "
                       "Prefer ready routes when equally suitable; missing media permission does not prevent planning. "
                       "Explain in Vietnamese.",
                       {"brief": brief, "options": options}, schema)
        if not isinstance(answer, dict) or set(answer) != {"choice", "reason"}:
            raise ValueError("Invalid AI route decision.")
        key, reason = answer["choice"], answer["reason"]
        if not isinstance(key, str) or key not in options or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 350:
            raise ValueError("AI selected an unapproved route or invalid reason.")
    selected = options[key]
    plan = {"method": selected["method"], "motion_ref": selected["id"],
            "reason": reason.strip(), "max_cloud_seconds": brief["max_cloud_seconds"]}
    if "billable_durations_seconds" in selected:
        plan["billable_durations_seconds"] = selected["billable_durations_seconds"]
    return plan
