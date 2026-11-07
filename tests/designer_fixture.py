"""Shared sample model-designed site; used only by isolated regression tests."""
from copy import deepcopy

DESIGN = {
    "brand": "Giấc Ngủ Việt",
    "page_title": "Tư vấn chọn nệm | Giấc Ngủ Việt",
    "description": "Tư vấn lựa chọn nệm với nội dung minh bạch, chờ xác minh.",
    "style": {
        "background": "#f7f2e7",
        "surface": "#fffdf8",
        "accent": "#356b57",
        "font": "editorial",
        "hero_layout": "split",
        "art": "orbit",
        "density": "airy",
        "cards": "elevated",
        "radius": 18,
    },
    "hero": {
        "eyebrow": "Lựa chọn phù hợp",
        "headline": "Tìm chiếc nệm phù hợp với bạn",
        "description": "Lắng nghe nhu cầu và giới thiệu giải pháp ngủ phù hợp.",
        "primary_action": "Nhận tư vấn",
        "secondary_action": "Khám phá",
    },
    "sections": [
        {
            "kind": "features", "variant": "grid",
            "eyebrow": "Lợi ích", "title": "Trải nghiệm tư vấn",
            "intro": "Những điểm cần cân nhắc trước khi chọn nệm.",
            "items": [
                {"title": "Nhu cầu", "body": "Tìm hiểu thói quen ngủ của gia đình."},
                {"title": "Không gian", "body": "Chọn kích thước tương xứng phòng ngủ."},
                {"title": "Chất liệu", "body": "Đối chiếu đặc điểm từng lựa chọn."},
            ],
        },
        {
            "kind": "faq", "variant": "list",
            "eyebrow": "Giải đáp", "title": "Câu hỏi thường gặp",
            "intro": "Giải đáp một số câu hỏi trước khi liên hệ.",
            "items": [
                {"title": "Nên bắt đầu từ đâu?", "body": "Xác định kích thước và thói quen."},
                {"title": "Có nên thử nằm?", "body": "Cảm nhận thực tế trước khi quyết định."},
            ],
        },
    ],
}

def revised_design():
    revised = deepcopy(DESIGN)
    revised["style"].update({
        "background": "#edf4ff", "surface": "#ffffff",
        "accent": "#285baa", "font": "modern",
        "hero_layout": "centered", "art": "geometry",
    })
    revised["hero"]["headline"] = "Khám phá giấc ngủ thoải mái mỗi ngày"
    revised["sections"] = list(reversed(revised["sections"]))
    return revised

def longer_design():
    long = deepcopy(DESIGN)
    long["style"].update({
        "background": "#141c25", "surface": "#242e38",
        "accent": "#d2ac6b", "font": "technical",
        "hero_layout": "editorial", "art": "minimal",
        "density": "compact", "cards": "bordered", "radius": 2,
    })
    long["hero"]["headline"] = "Tìm ý tưởng mới từ cấu trúc khác"
    long["sections"] = [
        {"kind": "story", "variant": "split", "eyebrow": "Tầm nhìn",
         "title": "Một câu chuyện", "intro": "Chúng tôi tập trung vào trải nghiệm.",
         "items": []},
        *deepcopy(DESIGN["sections"]),
        {"kind": "steps", "variant": "accent", "eyebrow": "Quy trình",
         "title": "Cách chúng tôi tư vấn", "intro": "Ba bước đơn giản.",
         "items": [
             {"title": "Trao đổi", "body": "Tìm hiểu nhu cầu."},
             {"title": "So sánh", "body": "Đánh giá lựa chọn."},
             {"title": "Liên hệ", "body": "Xác nhận thông tin."},
         ]},
        {"kind": "gallery", "variant": "grid", "eyebrow": "Ý tưởng",
         "title": "Không gian cảm hứng", "intro": "Minh họa bằng CSS, không phải ảnh thực.",
         "items": [
             {"title": "Ánh sáng", "body": "Không gian giản dị."},
             {"title": "Chất liệu", "body": "Kết hợp tự nhiên."},
         ]},
    ]
    return long
