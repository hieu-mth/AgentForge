"""Trusted, allowlisted media skill policies and lazy adapters.

No handler is imported at discovery time. The runner checks grants before dispatch.
"""
POLICY = {
    "media.compose": ("media_producer", "owner_gated",
                      frozenset({"workspace.write"})),
    "media.image_edit": ("media_producer", "owner_gated",
                         frozenset({"workspace.write"})),
    "media.quality_check": ("media_producer", "read_only",
                            frozenset({"workspace.read"})),
    "media.video_render": ("media_producer", "owner_gated",
                           frozenset({"workspace.write", "process.run"})),
    "media.tts": ("media_producer", "owner_gated",
                  frozenset({"workspace.write", "process.run"})),
    "media.copy_draft": ("media_producer", "owner_gated",
                         frozenset({"model.invoke", "workspace.propose"})),
}


def dispatch(skill_id, payload):
    if skill_id == "media.compose":
        from agentforge.media_assets import make_assets
        return make_assets(payload)
    if skill_id == "media.quality_check":
        from agentforge.media_quality import check
        return check(payload["run_id"])
    if skill_id == "media.image_edit":
        from agentforge.media_quality import edit_image
        return edit_image(payload["run_id"], payload["scene_index"], payload["operation"])
    if skill_id == "media.video_render":
        from agentforge.media_render import render_video
        return render_video(payload["run_id"], confirm_external_run=True)
    if skill_id == "media.tts":
        from agentforge.media_render import make_voiceover
        return make_voiceover(payload["run_id"], payload["engine"],
                              voice=payload.get("voice"), confirm_external_run=True)
    if skill_id == "media.copy_draft":
        from agentforge.media_pipeline import suggest_copy
        return suggest_copy(payload["topic"], payload["audience"], payload["goal"])
    raise PermissionError("No trusted adapter")
