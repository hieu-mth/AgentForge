"""Pure script parsing and shot beat analysis; no model, storage or worker dependencies."""
import re

SCRIPT_HEADING = re.compile(r"(?im)^[ \t]*(?:cảnh|scene)\s+[0-9]+\b")
AUTHORED_HEADING = re.compile(r"(?im)^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?(?:cảnh|scene)[ \t]+[0-9]+\b[^\r\n]*")
SCENE_TIME = re.compile(r"\((?:(\d+(?:[.,]\d+)?)\s*[–-]\s*)?(\d+(?:[.,]\d+)?)\s*(?:giây|s)\)", re.I)
TOTAL_TIME = re.compile(r"(?:thời lượng|video|phim)(?:\s+dài)?\s*[:=]?\s*(\d+)\s*(?:giây|s\b)", re.I)
SCRIPT_DIALOGUE = re.compile(r"(?m)^[ \t]*([^\W\d][^:\n]{0,27}):[ \t]*(\S[^\n]*)")


def needs_scene_analysis(text):
    return (len(text) > 500 or SCRIPT_HEADING.search(text) is not None
            or SCRIPT_DIALOGUE.search(text) is not None or "\n\n" in text.strip())


def script_ranges(script, count, seconds):
    headings = [match.start() for match in SCRIPT_HEADING.finditer(script)]
    if len(headings) > count:
        raise ValueError(f"Kịch bản có {len(headings)} cảnh đánh số. Hãy tăng số cảnh hoặc chia thành nhiều bản nháp.")
    dialogue = sum(len(match[2].split()) for match in SCRIPT_DIALOGUE.finditer(script)
                   if not SCRIPT_HEADING.match(match[1]))
    if dialogue > seconds * 3:
        raise ValueError("Thời lượng có thể không đủ cho các dòng lời thoại. Hãy tăng thời lượng hoặc chia kịch bản.")
    points = [0, *headings[1:], len(script)]
    while len(points) <= count:
        # Preserve explicit scene boundaries and prefer paragraph, then line, then word breaks.
        candidates = []
        for start, end in zip(points, points[1:]):
            section = script[start:end]
            first = len(section) - len(section.lstrip())
            last = len(section.rstrip())
            for separator in (r"\n[ \t]*\n", r"\n", r"\s+"):
                breaks = [match.end() for match in re.finditer(separator, section)
                          if match.start() > first and match.end() < last]
                if breaks:
                    middle = min(breaks, key=lambda at: abs(at - len(section) / 2))
                    candidates.append((end-start, start+middle))
                    break
        if not candidates:
            raise ValueError("Kịch bản không có đủ đoạn để chia theo số cảnh đã chọn.")
        points.append(max(candidates)[1])
        points.sort()
    return list(zip(points, points[1:]))


def duration_preference(brief, text):
    if brief["duration_mode"] == "manual":
        return brief["seconds"], "manual"
    declarations = {int(match[1]) for match in TOTAL_TIME.finditer(text)}
    if len(declarations) > 1:
        raise ValueError("Nội dung khai báo nhiều thời lượng khác nhau. Hãy giữ một mốc hoặc chọn thời lượng thủ công.")
    return (declarations.pop(), "script") if declarations else (None, "ai")


_CAMERA = re.compile(r"(?:camera|máy quay|góc máy|khung hình|framing)\b", re.I)
_GLOBAL_CONSTRAINT = re.compile(
    r"(?:phong cách|ánh sáng|màu sắc|style|lighting|negative prompt|ràng buộc chung|"
    r"yêu cầu chung|không|ưu tiên|giữ nguyên|no)\b", re.I)
_SCENE_CONSTRAINT = re.compile(
    r"(?:bối cảnh\s*:|(?:ràng buộc cảnh|yêu cầu cảnh|không đổi góc|scene constraints|"
    r"ánh nắng(?:\s+(?:buổi sáng|buổi chiều|ban mai))?\s+chiếu)\b)", re.I)
_GLOBAL_HEADING = re.compile(
    r"(?<!\w)\**(?:yêu cầu xuyên suốt|ràng buộc xuyên suốt|yêu cầu chung|"
    r"ràng buộc chung|global constraints|global requirements)\**\s*:\**\s*", re.I)
_SEQUENCE = re.compile(r",?\s+(?:sau đó|rồi|tiếp đó|sau đấy|then|and then)\s+", re.I)
_SCRIPT_CLAUSE = re.compile(
    rf"(?<=[.!?…;])\s+|\n+|,\s+(?=(?:{_CAMERA.pattern}|{_GLOBAL_CONSTRAINT.pattern}|"
    rf"{_SCENE_CONSTRAINT.pattern}))", re.I)


def scene_beats(source, *, last):
    heading, _, body = source.strip().partition("\n")
    timing = SCENE_TIME.search(heading)
    inline = heading[timing.end():].lstrip("* :—–-") if timing else heading.partition(":")[2].strip()
    actions, camera, constraints, global_constraints = [], [], [], []
    content = "\n".join(part for part in (inline, body) if part)
    if last and (header := _GLOBAL_HEADING.search(content)):
        global_constraints.extend(line.strip(" *-\t") for line in content[header.end():].splitlines()
                                  if line.strip(" *-\t"))
        content = content[:header.start()]
    for paragraph in re.split(r"\n\s*\n", content):
        for part in _SCRIPT_CLAUSE.split(paragraph):
            part = part.strip(" *")
            if not part:
                continue
            if _CAMERA.match(part):
                camera.append(part)
            elif _SCENE_CONSTRAINT.match(part):
                constraints.append(part)
            elif _GLOBAL_CONSTRAINT.match(part):
                (global_constraints if last else constraints).append(part)
            else:
                actions.extend(beat.strip(" ,;") for beat in _SEQUENCE.split(part) if beat.strip(" ,;"))
    return {"actions": actions, "camera": camera, "constraints": constraints,
            "global_constraints": global_constraints}


def shot_beat(actions, sequence, count, start_frame, frames, previous):
    if not actions:
        raise ValueError("Không tìm thấy hành động rõ trong cảnh. Hãy mô tả điều xảy ra trước khi tạo storyboard.")
    first = (sequence - 1) * len(actions) // count
    end = max(first + 1, sequence * len(actions) // count)
    assigned = actions[first:end]
    # When a scene has fewer actions than shots, allocate successive portions
    # of the same action. A static observation is valid; a new event is not.
    return {"assigned_text": " ".join(assigned)[:360], "start_frame_in_scene": start_frame,
            "end_frame_exclusive": start_frame + frames, "previous_shot": previous,
            "continued_action": sequence > 1 and (sequence - 2) * len(actions) // count == first}


