# Film Studio — local-first

Pipeline hiện có trong source: lập immutable film plan và shot slots → Owner review → ComfyUI motion job một lượt đã duyệt → nhận clip MP4, verify SHA/frames/FFmpeg → versioned production + optional local TTS → render episode có receipt → Owner review → publishing handoff local/optional private-only YouTube CLI.

Quy trình **không** tự tạo đầy đủ phim từ một prompt, không tự kiểm visual identity/continuity và không bảo đảm chất lượng media. Mỗi shot cần workflow, weights, nguồn nội dung và quyền được kiểm chứng. Tooling cho phép one-shot pilot; hiệu suất và khả năng dựng phim dài chưa được thử trên PC Owner.

- [Motion](../verification/MOTION.md)
- [Production](../verification/PRODUCTION.md)
- [Publishing](../verification/PUBLISHING.md)
- [Owner runtime acceptance](../verification/OWNER_PRODUCTION_GATE.md)

Mọi dữ liệu sản xuất và model giữ trong các vùng local của Owner, không thuộc cleanup Git.
