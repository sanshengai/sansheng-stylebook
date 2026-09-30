# 轻量出图（make 首版）

日常单图和文章组图使用简要计划。先完整读内容，挑值得画的要点；不要把文章中的事实改成装饰性图标。信息足够时直接给出推荐及一句理由，不逐层问用户。

## 简要计划

```json
{
  "version": 1,
  "scene": "wxillus",
  "style": "C42",
  "palette": {"family": "orig"},
  "reason": "用清楚的扁平画面解释两个方案的区别",
  "source": "article.md",
  "items": [
    {
      "position": "原文中准确的一句引用",
      "message": "读者应明白的一句话",
      "visual": "两张卡片分别呈现两个方案，并写明主体、动作和关系",
      "text": []
    }
  ]
}
```

`source` 相对 brief 所在目录解析；给文章配图时填写。`position` 是准确的原文引用，封面用 `cover`。每张图默认编号 01、02……；局部重出可提供稳定的 `id`。`text` 可为空、单句或句子列表。整组 `format` 或逐张 `format` 可指定已有静态格式；wxillus 中的 cover 自动采用公众号头条尺寸。

已有角色或画风参考可放整组 `references: [{"role": "identity", "path": "character.png"}]`，路径也相对 brief。职责沿用编译器的画风、身份、姿势、构图等分类；用户提供 `role: style` 时优先使用该图，替代合同默认锚点。

可传 `sb2:` 或旧 `sb1:` 码到 `code`；码优先于明说画风和配色。sb2 自带用途，brief 可以省略 scene；两处都有用途时必须一致。品牌色如 `sb2:info/C42-hex.1F6F8B.F4F1E8`。教材用途、自动返修和飞轮捕获仍在接入。网站 sb2 复制按钮尚未完成。

## 一条命令执行

```sh
python3 scripts/sb.py make brief.json -o 新目录
```

默认四路生成（`--jobs 1–8`）。使用已配置的外部服务，可加 `--provider`、`--model`、`--quality`。画风优先级：码 → 本次指定 → 用户确认的偏好 → 作者档案 → 出厂默认。观察中的偏好不自动改变默认。

生成原图、最终导出、逐图输入与凭证、`overview.png` 和 `report.json`。不覆盖已有目录；失败原图和其他成功候选保留。鉴权失败停止尚未开始的任务。

Agent 看总览并按需打开原图：字是否准确、主体与关系有无错画、裁切有无损失。源码绑定变化或像素失败的候选不能采用。报告中 `pending_visual_review` 只说明像素预检通过，未证明内容或吸引力；当前首版没有自动回写看图采用或单张返修，应保留宿主看图结论，并另开候选目录修图。

## Codex 内置生图

```sh
python3 scripts/sb.py make brief.json -o 新目录 --prepare
```

这一步不调用外部服务，输出状态 `pending_host`。按 `prepared.json` 的每个任务，将完整 `compiled.prompt` 和全部 `compiled.references[].path` 交给内置工具，不再改写锁定层。保存内置工具原图及实际调用参数，以 `--prepared prepared.json --import-results host-results.json -o 新目录` 导回。记录格式见下例。未知底层模型和费用保持 `null`；`seconds` 是工具调用实测耗时，可为 `null`。导回报告的总耗时只涵盖导回和导出，完整流程应另行计时。

```json
{
  "version": 1, "prepared_sha256": "prepared.json 文件的 SHA256",
  "images": {"01": {
    "provider": "codex_builtin", "model": null, "est_usd": null, "seconds": 31.0,
    "path": "/实际工具原图.png", "sha256": "原图 SHA256",
    "prompt_sha256": "完整 compiled.prompt UTF-8 SHA256", "reference_sha256s": [],
    "tool_arguments": {"prompt": "完整 compiled.prompt", "referenced_image_paths": [], "transparent_background": false}
  }}
}
```

每个任务必须都有对应记录；摘要和参数必须来自实际调用。输入或合同变化会拒绝导回，不能把旧成图绑定到新提示词。C42 旧参考图已因真实试跑不符合画风要求而停用；保留历史文件，但默认只使用合同提示词，直到有确认过的新参考图。

带大量文字、教程数据或准备正式发布时，现阶段继续使用 [planning.md](planning.md)、[text.md](text.md)、[qa.md](qa.md) 中已有的计划与独立复核；发布档尚未整合进 make，不能仅凭本入口完成正式封存。
