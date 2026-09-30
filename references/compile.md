# 编译：配方清单 → 提示词

实现：`scripts/stylebook/compile.py`。同一份清单编译两次逐字相同，并给出清单指纹 `manifest_hash`。

S02 公众号头条封面的方形母版与扩图使用 `sb.py cover-flow`；它保留普通清单，分别输出 1:1 母版和 2.35:1 扩图提示词。执行与验收见 [cover-flow.md](cover-flow.md)。

## 清单字段

```json
{
  "style": "C31",                       // 必填；C31@r2 表示锁定修订号
  "model": "gpt-image-2",               // 目标模型，决定方言；缺省 gpt-image-2
  "format": "xhs-carousel",             // 可选；决定默认比例、安全区、默认文字档位、导出像素
  "aspect": "3:4",                      // 可选；缺省取格式的比例，再缺省 1:1
  "content": {
    "subject": "……",                    // 必填：画什么（英文效果最稳）
    "inventory": "Exactly two people and one cup; no background person", // 可选：人数与物件数量，按字面执行
    "characters": [{"id": "A", "desc": "……"}],
    "relations": "谁在谁左边、谁看着谁",
    "camera": {"shot": "", "angle": "", "lens": "", "focus": "", "composition": ""},
    "lighting": "", "background": "", "purpose": "", "mood": ""
  },
  "structure": "flow | auto",           // 讲道理的图才写
  "density": "sparse | balanced | dense",
  "palette": {"family": "orig", "light": 0, "sat": 0, "custom": []},
  "text": {"mode": "native | overlay | none", "items": [{"role": "title", "text": "……", "position": "top"}], "font": ""},
  "references": [{"path": "ref.png", "role": "style | identity | identity_face | pose | composition | background | product"}],
  "use_anchor": true
}
```

## 段落顺序（固定）

锁定层 → 主体（含角色）→ 画面元素数量 → 空间关系 → 必须表达的要点 `content.points` → 镜头 → 光线 → 色彩 → 背景 → 结构与密度 → 用途与情绪 → 文字 → 画幅与安全区 → 硬约束（合同要求前置时放最前）→ 模型变体补充。

位图 `overlay` 的每条 `text.items` 另须填写最终导出尺寸上的相对 `box: [x,y,w,h]`；完整写法见 `text.md`。PPT / 课件可编辑文字由 `pptx` 后续写入时不填 box。

## 规则

- **锁定层**：合同 `recipe.positive` 原样放最前，任何人不改写。
- **结构专用规则**：合同可设 `recipe.structure_prompts.<structure>`；只有清单明确填写同一个 `structure` 时，编译器才在结构段后加入该规则。人物等无结构题不会读到流程专用指令。
- **画面元素数量**：`content.inventory` 只写题材事实中有明确数量或排除要求的人、物、字；不把画风限制或验收器的主观判语塞进这里。未填写时提示词保持原样。
- **必要信息**：`content.points` 写本张图可核对的事实、文字或空间关系。例如「屏幕内有表格和放大镜」，不能仅靠这两个图标要求看图员证明「查询的是真实数据」。来源与创作用意留在原文计划、`why` 或 `content.purpose`；跨图顺序另做整组核对。关键意思若必须靠文字才能明确，列入 `text.items` 或换表达方式，不能删掉核心事实来争取通过。精确像素与画幅比例写在格式和尺寸配置中，用实际图像量测证明。
- **冲突词**：内容里出现合同 `prompt_bans` 中的词就拦下（大小写、连字符、下划线、空白都视为相同，按整词匹配）。改内容描述或换样式，不删冲突词。
- **换色**：合同 `palette.recolor` 为 `locked` 时只能原色；`lightness_only` 只能调深浅；`free` 可换色系。深浅与鲜灰按 OKLCH 固定算法从色系 hex 推出（`palette.py`，网站选择器用同一算法），写进提示词的是「颜色名 + hex」。
- **参考图**：每张写明职责（画风 / 角色身份 / 姿势 / 构图 / 背景 / 必须出现的实物）；合同登记了锚点图时自动放第一张作画风参考，并把 `anchor.isolation` 原文写进该参考图的隔离说明。清单设置 `use_anchor: false` 时，两者都不使用。`composition` 只借用必要元素的位置、大小、视觉主次和空间关系，不借用草图的灰度、笔触、材质、文字或偶然道具；成图仍以风格合同与清单内容为准。
- `identity` 会要求继承标志性服装；只需同一个人的五官、发型、眼镜或发饰而要换装时，裁出头部参考图并用 `identity_face`，服装与场景在 `content.subject` 指定。
- 验收未发布的候选合同时，`sb.py qa <图> --style C58 --contract <候选合同.json> --manifest <清单.json>` 会按候选的 `qa` 条款复核，并检查风格码与清单修订号；省略 `--contract` 才读取正式合同。候选通过仍不等于正式准入。
- **修订锁定**：清单写 `C31@r2` 而合同已是 r3 时拦下，先问用户是否升级。
- **尺寸**：按比例和模型算生成尺寸（16 的倍数、长边默认 1536、比例不超过 3:1）；gpt-image 系列总像素须在 655,360 到 8,294,400 之间。中转返回的尺寸可能与请求不同但比例一致，导出时再裁切缩放。
- **背景透明度**：普通格式和未指定格式的矩阵题都在提示词中要求整幅背景不透明，避免信息图出现半透明四角；`sticker-grid` 等显式透明格式不加这条。导出仍检查原图 alpha，提示词不能代替像素验收。

## 方言

| 家族 | 模型 | 写法 |
|---|---|---|
| gpt-image | gpt-image-2 等 | 分段标签式；参考图写成「Image 1: …」；中文用「」括起 |
| gemini / seedream | Gemini、Qwen、万相、Seedream | 合成连贯叙事段落，不写排除清单；Seedream 参考图用中文「图一：…」 |
| flux | Flux | 锁定层与主体放最前（越靠前权重越高） |
| midjourney | Midjourney | 单段 + `--ar` 与 `--no`（取冲突词前 8 个） |
