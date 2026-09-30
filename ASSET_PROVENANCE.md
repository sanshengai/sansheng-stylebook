# Style anchor provenance

The 48 bundled `styles/C*/anchor.png` files are visual references for prompt compilation. They are **not** evidence that a style has passed quality admission or that every subject and format works.

`styles/anchor-provenance.json` records each distributed file's SHA-256, its project source image's SHA-256, and the known generation route. Forty-five anchors are resized from this project's same-topic image test. C10, C24, and C31 use newly generated subject-neutral styleboards because their original tests carried unwanted subject or layout details into later images. The source images and detailed test receipts stay outside this public package; no local user path is needed to verify the distributed anchors. Run `python3 scripts/stylebook/anchor_provenance.py` to compare the public ledger, the files, and the style contracts.

The old batch requested `gpt-image-2` through its OpenAI route. The response records do not prove the underlying model ID, so the ledger says “requested.” Later Codex built-in generations likewise have no exposed underlying model ID. The reference prompts were informed by the MIT-licensed projects named in `THIRD_PARTY_NOTICES.md`; the generated image files were made for this project. Image provenance does not replace content and visual review before reuse.

The README previews are unedited copies of project same-topic outputs: `assets/C01-story-sample.png` is C01-q1 (SHA-256 `acc2a9767da459bd743a59bb49833f043755b7eecf810e540a6792bf7b11aee9`), and `assets/C32-infographic-sample.png` is C32-q3 (SHA-256 `f41571c36d6a6a222c63464ea2ea6c3cff0b86e42f8635a7c7db4c43c1b1277b`). They show particular successful test images, not a guarantee for a different topic or a full series.

The MIT license in `LICENSE` covers the repository's original code, text, and bundled project images to the extent the contributor has rights to license them. Third-party code and text retain the notices in `THIRD_PARTY_NOTICES.md`.

## 2026-09-30 C42 默认参考停用

C42 历史 anchor.png 保留原始字节和来源摘要。真实文章试跑发现其绘本画法与清透扁平合同不符，并带入未请求人物和背景；合同修订 3 将 `anchor.enabled` 设为 false，编译器和默认看板不再引用。三张替代样板均未通过，未纳入公开资产。参考文件存在不代表正式准入。
