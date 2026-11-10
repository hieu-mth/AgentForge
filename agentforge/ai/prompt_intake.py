"""Prompt-first owner intake: deterministic, explicit scope; never executes AI.

Maps a natural-language request to an allowlisted S4 template. Ambiguous
intents remain unplanned until clarified; no unsafe freeform tool dispatch.
"""
import re
import unicodedata
from uuid import uuid4

from agentforge import brain_planner, goal_preflight, workspace_policy

MAX_PROMPT = 6000


def _fold(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower())
                   if unicodedata.category(c) != "Mn").replace("đ", "d")


def plan_request(prompt, *, max_model_calls=1, max_external_runs=0,
                 brain_db_path=None, analytics_db_path=None, growth_db_path=None,
                 policy_db_path=None):
    if (not isinstance(prompt, str) or not 20 <= len(prompt.strip()) <= MAX_PROMPT
            or any(ord(ch) < 32 and ch not in "\n\t" for ch in prompt)):
        raise ValueError("Yêu cầu phải dài 20–6000 ký tự, không chứa ký tự điều khiển.")
    if type(max_model_calls) is not int or not 0 <= max_model_calls <= 3:
        raise ValueError("Giới hạn model phải từ 0 đến 3.")
    if type(max_external_runs) is not int or max_external_runs != 0:
        raise PermissionError("Prompt intake không cấp quyền chạy tiến trình ngoài.")
    text = prompt.strip()
    normalized = _fold(text)
    wants_website = any(k in normalized for k in (
        "website", "landing page", "trang web", "web ban", "web gioi thieu",
        "trang gioi thieu", "thiet ke web"))
    wants_storyboard = any(k in normalized for k in (
        "storyboard", "kich ban video", "noi dung video", "video script"))
    # Explicit video-making verbs are a valid intent even when the Owner
    # doesn't know the technical word "storyboard". The prompt workflow can
    # prepare a script only; it MUST NOT imply that an MP4 is auto-rendered.
    wants_video = wants_storyboard or bool(re.search(
        r"\b(?:tao|lam|dung|san xuat|render|xuat|edit|chinh sua)\s+"
        r"(?:mot|1|video|clip|doan|phim|video ngan|video quang cao)?\s*"
        r"(?:video|clip|phim|mp4)\b", normalized)) or bool(re.search(
        r"\b(?:video|clip)\s+(?:quang cao|gioi thieu|tiktok|reels|shorts)\b",
        normalized))
    # Full-role requests such as "AI Architect ..., AI Developer ..., QA ...,
    # AI Reviewer ..." are intentional V5 requests, even without a magic
    # English prefix. The ordinary "AI Developer" prompt remains single-role.
    full_company_roles = (
        all(role in normalized for role in ("ai architect", "ai developer", "ai reviewer"))
        and any(role in normalized for role in ("qa", "kiem thu", "kiem tra"))
    )
    wants_company = full_company_roles or any(k in normalized for k in (
        "ai company v5", "agentforge v5", "software company v5",
        "cong ty ai v5", "multi agent v5"))
    wants_advanced = any(k in normalized for k in (
        "ai developer", "react tuy bien", "web app tuy bien",
        "webapp tuy bien", "ung dung react tuy bien", "ai viet code"))
    wants_webapp = any(k in normalized for k in (
        "shopee", "marketplace", "san thuong mai dien tu",
        "thuong mai dien tu", "gio hang", "web app", "webapp",
        "ung dung mua sam", "ecommerce"))
    if wants_website and wants_video:
        return {"status": "NEEDS_CLARIFICATION",
                "message": "Yêu cầu đang gồm cả website và video. Hãy tách thành hai công việc độc lập để bạn duyệt từng sản phẩm."}
    if wants_company:
        slug = "company-" + uuid4().hex[:12]
        template = "webapp.company"
        inputs = {"slug": slug, "brief": text}
        title = "V5 AI Company: Architect → Developer → QA → Reviewer"
        if max_model_calls != 3:
            raise ValueError("V5 cần 3 lượt model dự kiến trong Cài đặt/Goal. Chưa gọi AI.")
    elif wants_advanced:
        # Advanced source generation is explicit opt-in, never inferred from
        # marketplace keywords. Owner still approves model & source SHA.
        slug = "code-" + uuid4().hex[:12]
        template = "webapp.develop"
        inputs = {"slug": slug, "brief": text}
        title = "AI Developer thử nghiệm: đề xuất mã nguồn React tùy biến"
    elif wants_webapp:
        # Only a trusted local marketplace scaffold, NOT arbitrary AI code.
        slug = "app-" + uuid4().hex[:12]
        template = "webapp.draft"
        inputs = {"slug": slug, "brief": text}
        title = "Tạo ứng dụng marketplace demo React để Owner duyệt"
    elif wants_website:
        # A new slug ensures no overwrite. User-provided prompt is never auto-executed.
        slug = "web-" + uuid4().hex[:12]
        template = "website.draft"
        inputs = {"slug": slug, "brief": text}
        title = "Thiết kế website theo yêu cầu owner"
    elif wants_video:
        template = "creative.storyboard"
        # The template's bounded slots require nonempty fields.
        inputs = {"topic": text, "audience": "Khách hàng quan tâm đến sản phẩm",
                  "goal": "Tạo storyboard dự thảo để owner xem xét"}
        title = "Bước 1/2: Tạo storyboard video để Owner duyệt (chưa render MP4)"
    else:
        return {"status": "NEEDS_CLARIFICATION",
                "message": "Hiện Workspace hỗ trợ website/React và lập storyboard video. Để tạo video, hãy ghi 'Tạo video quảng cáo...' hoặc 'Viết storyboard...'. Kế hoạch prompt chỉ tạo kịch bản; MP4 cần bước render local riêng sau khi duyệt."}
    policy = workspace_policy.read(db_path=policy_db_path)
    if (template in {"website.draft", "webapp.draft", "webapp.develop", "webapp.company"} and not policy["website_enabled"] or
            template == "creative.storyboard" and not policy["storyboard_enabled"]):
        raise PermissionError("Role/workflow đã bị owner tắt trong Settings.")
    if max_model_calls > policy["max_estimated_model_calls"]:
        raise PermissionError(
            "WORKSPACE_MODEL_CAP_EXCEEDED: Kế hoạch cần "
            f"{max_model_calls} lượt model/Goal, giới hạn hiện tại là "
            f"{policy['max_estimated_model_calls']}. Vào Cài đặt → "
            "Prompt Workspace để thay đổi và xác nhận; chưa gọi AI."
        )
    if max_model_calls < 1:
        raise ValueError("Workflow này cần tối thiểu 1 lượt model dự kiến.")
    goal_preflight.require_ready(
        template, inputs, analytics_db_path=analytics_db_path,
        growth_db_path=growth_db_path)
    goal = brain_planner.propose(
        title, template, inputs, max_model_calls=max_model_calls,
        max_external_runs=0, db_path=brain_db_path)
    return {"status": "PLAN_CREATED", "goal_id": goal["goal_id"],
            "template": template,
            "next_step": ("OWNER_REVIEW_STORYBOARD_THEN_LOCAL_RENDER"
                          if template == "creative.storyboard" else None),
            "model_dispatched": False,
            "requires_owner_approval": True, "published": False}
