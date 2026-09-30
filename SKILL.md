---
name: sansheng-stylebook
description: 叁笙画风手册（公开 beta）。用固定的风格码把文章、课件、故事做成风格统一的一组图：封面、文章配图、小红书卡片、PPT、信息图、四格漫画、绘本、分镜首帧、播客与音乐封面、表情包。用户给出风格码（sb2:… / sb1:… 或 C31 这类样式码）、说「用叁笙画风手册 / 画风手册出图」、或要求检查、配置本 Skill 的生图服务时使用。只做静态图，不做视频与 Logo。
---

# 叁笙画风手册

一句话：**选一次风格，所有图都是这个味道。** 风格由「风格合同」锁定，提示词由编译器按固定顺序生成，每张图出完都要验收。

> 公开 beta。下文「现在能做」列的是已实现的；仍处试用或尚未实现的用途须如实告诉用户。

## 现在能做 / 还没有

| 能力 | 状态 | 入口 |
|---|---|---|
| 按风格码或样式码编译提示词 | 能做 | `sb.py compile` |
| 简要计划一条命令出图、导出、像素预检与总览 | 首版可用；待宿主看图，自动返修、飞轮与发布档尚未接入 | `sb.py make` / `references/quick.md` |
| Codex 内置生图 | 能做；先编译，再把完整提示词和参考图交给当前会话的内置生图工具 | `references/backends.md` |
| S02 公众号头条封面方形优先编译 | 仅在作者私有 profile 中试验；公开包没有 S02 | `sb.py cover-flow` |
| 出图（OpenAI 及兼容中转、Gemini、OpenRouter、火山 Seedream、通义万相；繁忙自动重试并切备用线路） | 能做 | `sb.py generate` |
| 首次配置、三态自检、无服务时的收件箱 | 能做 | `sb.py setup` / `doctor` / `inbox` |
| 给一篇文章定配图计划（自动模式）：定样式、找位置、判信息形状、定结构与密度 | 能做 | `sb.py style-for` / `plan` / `plan-review` |
| 自动推荐与局部手动选择的版本化记录 | 本地画廊可导入/导出并与 CLI 往返；官网入口待接入 | `sb.py selection` / `references/selection.md` |
| 记住明确偏好、观察独立任务中的主动改选；可查看、撤销、忘记和暂停 | 能做；真实个人化效果仍需使用中复核 | `sb.py preferences` / `references/preferences.md` |
| 一口气出完一组图：出图 → 导出 → 验收 → 单张返修；系列母版验收通过后才用作画风参考 | 能做 | `sb.py batch` |
| 按平台裁切导出（公众号头条另存方形等） | 能做 | `sb.py export` |
| PPT：整页图，或插画 + 可编辑文字 | 能做 | `sb.py pptx` |
| 角色设定网格、身份参考、一致性核对、项目锁定 | 能做（最小可用） | `sb.py character` |
| 出图验收（像素、看图、中文逐字比对、对照网格；独立性见验收来源） | 能做 | `sb.py qa` / `sheet` |
| 8 题测试矩阵、注册表、本地画廊 | 能做（维护者用） | `sb.py matrix` / `build` |
| 表情包透明底切片 | `sticker-grid` 导出后用 `sb.py sticker-split <宫格.png> --grid 3 -d <新目录>`；也可用可选的 `sticker-single` 逐张导出，用 `sb.py sticker-check <目录> --count 9` 检查成套像素，再逐张看图。单图路线尚未完成独立整组准入 | `references/formats.md` |
| 单页多格漫画逐格切片 | 还没有 | — |

**55 种样式均有可调用合同**：公开版 53 种，私有 profile 2 种。48 种待准入公开样式已配画风锚点；容易串入原图题材的 C31、C24 改用无题材样板。批量系列优先选正文图作母版，验收通过后后续图才引用；只生成未验收的母版不能传播。合同表示可以编译提示词和试出图，不表示已通过正式准入；未准入样式须如实说明仍待跨题材和实际版式验证。公开版不会包含 S01、S02。编译时报「找不到风格」时，先核对风格码和私有 profile 是否已加载。

## 路由：先判断用户要什么

**轻量入口首版**：用户明确要求快速试图、简要计划或 `make` 时，读 `references/quick.md`。外部服务一条命令出图，内置工具用 `--prepare`。不把像素预检或准备完成误记为正式验收；发布档继续按下列现役路径执行。

1. **消息里有风格码或网页选择 JSON** → 读 `references/selection.md`，用 `sb.py selection normalize` 归一化并核对场景、修订、作用范围；再按 3、4 走。`sb2:` 可传用途、修订、色调或品牌 HEX；旧 `sb1:` 仍可读，逐图设置继续用语言或 JSON。网页配置不包含原文提炼结果，仍需先读内容；网页不会代替编译器生成完整提示词。
2. **第一次用 / 出图报「没有可用的生图服务」/ 用户问怎么配置** → 当前会话有 Codex 内置生图工具时直接走第 3 步；否则读 `references/setup.md`，跑 `sb.py doctor`，按向导配置。**绝不让用户把密钥贴进对话**，也不替用户写密钥文件。
3. **要出单张或几张图** → 如果图来自文章、课件或讲稿，即使只出一张，也先按第 7 步对照完整原文做单项内容计划与复核；再读 `references/compile.md` 写编译清单并运行 `sb.py compile 清单.json --json`。当前会话有 Codex 内置生图工具时，按 `references/backends.md` 把编译结果的完整 `prompt` 与 `references[].path` 交给该工具；否则用 `sb.py generate`。`model` 是编译方言，不代表内置工具的实际模型 ID。
3a. **作者私有 profile 中的 S02 公众号头条封面** → 读 `references/cover-flow.md`，用 `sb.py cover-flow` 编译方形母版与横向扩图两段提示词；先验方形，再扩图和正式导出验收。公开包没有 S02，不能把这条路由推荐给未安装私有 profile 的用户。
4. **每张图出完** → 读 `references/qa.md` 验收；不合格按原因单张返修，最多重试 2 次，仍不合格就把图和原因交给用户。
5. **图里要有中文字** → 另读 `references/text.md`。
6. **出图报错（额度、繁忙、密钥、组织验证、内容被拒）** → 读 `references/backends.md`。
7. **给一篇文章配图 / 做一套小红书卡片或 PPT** → 读 `references/planning.md` 写 `plan.json`，`sb.py plan` 检查；文章新计划用 v3 `coverage` 逐项记录核心内容的画／不画决定，出图前运行 `sb.py plan-review`，有漏项就保留旧计划与报告、修订并复核。已有配图须核对实际文件和画面；若全部核心项已覆盖，允许零新增图，独立复核通过后直接结束本次配图，不运行 `batch`。复核服务暂不可用时可试图，但标记“内容规划待复核”，不能称完整组已验收。尚未确定内容与样式时给用户确认表，已有明确授权或项目锁定则直接执行。已配置外部服务时可用 `sb.py batch`；使用 Codex 内置生图时，用 `sb.py plan --manifests` 生成逐张清单，逐张编译、出图、导出、验收。系列先选正文或样板图作母版，只有独立看图通过才作为后续图的画风参考；验收失败就停在该依赖点。PPT 再用 `sb.py pptx` 组装。版式规格见 `references/formats.md`。
7a. **系列里有固定角色** → 读 `references/consistency.md`：先写角色圣经、出设定网格，之后每张拿它当身份参考；系列写项目锁定文件。
7b. **用户说“以后都这样”、要求记住或清除偏好** → 读 `references/preferences.md`，用 `sb.py preferences` 写入或管理；单次改图只改本次计划。
7c. **用户用语言改整组或某张** → 按 `references/selection.md` 更新选择记录，用 `selection impact` 找受影响图片；精炼文字仍由宿主对原文改写并复核。局部修改若碰到系列母版，先明确是单图候选还是替换全系列母版。
8. **维护者：给样式跑测试、准入、重建注册表与画廊** → 读 `references/matrix.md`。

## 硬规则

- **锁定层原样使用**：风格合同里的 `recipe.positive` 一字不改，编译器负责放在最前；不要在编译结果外再「润色」提示词。
- **一篇 / 一个系列只用一个样式**；换样式要用户明说。
- **冲突词拦截不绕过**：编译报「冲突词」时改内容描述或换样式，不许删掉合同里的冲突词。
- **颜色锁定的样式不换色**：合同 `palette.recolor` 为 `locked` 时只能原色。
- **计划确认**：内容、样式或比例尚未确定时，给一张计划表供用户确认一次；已有明确授权或项目锁定时直接做完，中途只在真需要用户决定时停。
- **不编造能力**：区分「有基础合同、可试出图」和「已通过正式准入」；还没实现的版式直接说还没有。未准入样式不能据单张样图宣称稳定，也不能据此切换现有写作出图流程。
- **成本**：`sb.py generate` / `batch` 的服务调用写进 `logs/cost.jsonl`；Codex 内置工具不经该日志，不推断其底层模型 ID 或单张费用。首次调用另行付费的外部服务前告诉用户单价量级。
- **密钥**：只放环境变量或 `~/.config/sansheng-stylebook/.env`（权限 600）；配置文件、对话、日志里都不出现密钥。

## 风格码

```
sb1:<样式>[-<结构>-<密度>]-<色彩>
  样式  C31 或 C31@r2（@r 锁定修订号；合同已升级时编译会拦下，先问用户是否升级）
  结构  auto 或表达结构 id（flow、compare、pyramid…，见 structures/structures.json）；只在讲道理的场景出现
  密度  auto / sparse / balanced / dense；与结构成对出现
  色彩  orig，或 <色系 id>.L<深浅>S<鲜灰>（-1 / 0 / 1）；品牌色须改用 selection JSON 写入具体 HEX
例：sb1:C01-orig　sb1:C31-flow-balanced-macaron.L1S0
```

结构 `auto` 在文章/系列计划中由宿主逐张根据原文形状判定并写依据句；单张无内容计划时编译器仍写入「按内容选最清楚的结构」。密度 `auto` 由原文要点数决定；固定密度与要点数不符时，计划校验会拒绝。

## 常用命令

所有命令在本 Skill 根目录执行：`python3 scripts/sb.py <命令>`。

| 命令 | 用途 |
|---|---|
| `compile 清单.json [--json]` | 只编译，打印提示词（或含尺寸、参考图的完整结果） |
| `cover-flow 清单.json` / `cover-check 方形.png` | S02@r3 公众号头条封面：编译方形母版与扩图提示词，预检方形的高对比内容边距 |
| `generate 清单.json -o 图.png [--provider --model --quality]` | 编译并出图 |
| `qa 图.png --style C31 [--manifest 清单.json] [--text "标题|标签"] [--format 版式]` | 验收单张；带清单核对内容，需缩略图或居中方形的格式还会检查实际导出预览；退出码 1 = 不合格 |
| `qa-contrast 已知问题图.png 候选图.png --defect-file 禁止特征.txt` | 维护者：匿名换序比较一个可见缺陷；只证明相对改进，不算整张通过或样式准入。若写希望满足的正向特征则用 `--criterion-file` |
| `qa-focus 局部.png --original 整图.png --criterion-file 判据.txt` | 维护者：同一局部缺陷做两次独立绝对复核；须先在已知反例上验证会拒绝，不算整张通过或样式准入 |
| `sheet 定妆图 其他图… -o 对照.png` / `sheet 图 --thumbs -o 缩略.png` | 一致性对照网格 / 小尺寸可辨认检查 |
| `doctor [--deep]` / `setup` / `inbox 清单… -d 目录` | 自检 / 配置向导 / 收件箱 |
| `style-for 场景` / `plan 计划.json` / `plan-review 计划.json --article 原文` | 定样式 / 检查计划并出确认表 / 独立复核计划 |
| `batch 计划.json -o 目录` / `export 图 --format 格式 -o 输出` / `pptx 计划.json --images 目录 -o x.pptx` | 一口气出完 / 按平台导出 / 组装 PPT |
| `character sheet 角色.json --style X` / `character check 角色.json 设定图 图… --style X` | 角色设定网格 / 一致性核对 |
| `matrix 样式码` / `build [--private] [--gallery] [--check]` | 维护者：测试矩阵 / 注册表与画廊 |

## 数据在哪

- 样式目录 `styles/catalog.json`，风格合同 `styles/<码>/contract.json`（Schema：`styles/_schema/contract.schema.json`）。
- 格式 `formats/formats.json`、表达结构 `structures/structures.json`、色系 `palettes/palettes.json`、场景与出厂默认 `scenes/scenes.json`。
- 网站与 Skill 共用的注册表 `registry.json`（由 `sb.py build` 生成，不手改）。
- 作者自己的私有样式与默认值放私有 profile：环境变量 `STYLEBOOK_PROFILE`，或 `~/.config/sansheng-stylebook/profile/`；有它时，作者档案里的场景默认优先于出厂默认。
