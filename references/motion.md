> **旧版，动态版阶段将替换。** 动图用途已从官网选择器和用途池下架，`sb.py motion` 命令实现暂时保留，仅供旧流程使用。

# 动图（可选子板块）

只做**局部动、其余不动**的轻动效，不重画像素，所以画风不会漂。不默认走图生视频（每段几元、GIF 体积大、画风会漂）。状态：4 个模板（glow、particles、breathe、labels）和按平台降档的编码器已实现，可出 GIF 或动画 WebP（`sb.py motion`）；公众号、微信聊天、X 的真机预览结果未确认前，不对外承诺能自动播放。

## 什么时候做

- 文章里 1–2 张关键图想要「呼吸感」：光晕、飘动粒子、轻微缩放或两层视差，2–3 秒循环。
- 自家形象的微信表情（240×240，≤ 500KB，一套 16 或 24 张）。
- X 或网站用 MP4 或 ≤ 15MB 的 GIF。

## 平台出口（需真机复核）

| 平台 | 约束 |
|---|---|
| 公众号后台手动插入 | GIF 素材 ≤ 10MB；建议目标 ≤ 3MB、宽 480–720 |
| 公众号接口发草稿 | 正文图只收 jpg/png 且 ≤ 1MB，GIF 可能被拒，自动发布链要另测 |
| 微信表情 | 240×240，≤ 500KB；品牌形象属推广类，不在商店展示 |
| X | GIF ≤ 15MB |
| 小红书 | GIF 口径不一，优先实况照片或 MP4 |

## 做法

```sh
python3 scripts/sb.py motion 通过验收的图.png --template glow --region 0.55,0.1,0.4,0.5 --target wechat-article -o 输出.gif
```

模板 `glow` 光晕脉冲、`particles` 飘动粒子、`breathe` 轻微呼吸缩放；`--region` 是作用区域占画面的比例 x,y,w,h，区域外每一帧完全相同（测试保证）；`--target` 为 `wechat-article`（≤3MB）、`wechat-sticker`（240×240 居中裁方，≤500KB）、`x`（≤15MB）。编码器从原尺寸开始逐档降宽度、帧率、颜色数，降到最低仍超预算就报错且不留文件。

流程：
输入是已通过验收的静态 PNG 和一个作用区域；选一个动效模板；按目标平台自动降档（尺寸、帧率、颜色数）；输出 GIF 或 WebP；发布前在对应平台预览一次。

## 收到 `sb2:motion/<码>` 时

官网复制出来的动图码形如 `sb2:motion/C34`，`motion` 是用途 id，`C34` 是画风。按这个顺序做：

1. 先判断用户要哪一类：文章动态插图（要点依次出现，模板 `labels`）、表情包（模板 `breathe` 或 `particles`，目标 `wechat-sticker`）、X 动图（模板 `glow` 或 `particles`，目标 `x`）。用户没说就按内容推断，信息图或带要点的文章插图默认按文章动态插图的 `labels` 做。
2. 先按对应场景出静态图，别跳过：文章动态插图按 [scenes/wxillus.md](scenes/wxillus.md) 或 [scenes/info.md](scenes/info.md) 出图；表情包按 `scenes/scenes.json` 里 `id=sticker` 的场景出单角色图；X 动图按 [scenes/wxcover.md](scenes/wxcover.md) 出 16:9 图。画风用码里的那个（如 `C34`）。
3. 静态图通过验收后，用 `python3 scripts/sb.py motion` 做局部动效；`labels` 模板要给 `--boxes` 或 `--layout`，`--target` 按出口选（`wechat-article`、`wechat-sticker`、`x`、`web`）：

   ```sh
   python3 scripts/sb.py motion 静态图.png --template labels --boxes "0.05,0.04,0.7,0.12" --target wechat-article -o 动图.gif
   ```

4. 交付 GIF（平台用）和 WebP（网页预览用），并说明公众号、微信、X 的真机播放尚未验证。

## 标签依次出现（labels）

给信息图、文章插图用：开头只显示「标签区域被抹平」的版本，标签按阅读顺序逐个淡入（每个约 0.4 秒，相邻约 0.25 秒），全部出现后停留约 1.5 秒再回到起点循环；`--no-loop` 则播完停在最后一帧。抹平用方框外一圈的颜色按行插值再加细颗粒，方框外像素逐帧不变，最后一帧与原图逐像素一致（测试保证）。

```sh
python3 scripts/sb.py motion 信息图.png --template labels --boxes "0.05,0.04,0.7,0.12;0.15,0.2,0.3,0.08+0.15,0.29,0.35,0.05" --target web -o 信息图.webp
python3 scripts/sb.py motion 信息图.png --template labels --layout overlay配置.json --target wechat-article -o 信息图.gif
```

- `--boxes` 每个框是画面比例 `x,y,w,h`，用分号分隔、按出现顺序；同时出现的几个框用 `+` 连接（例如步骤的标题和说明）。框不能重叠、不能越界。
- `--layout` 读 overlay 排字配置里 `items[].box`，按 items 顺序出现；hybrid 模式只取 `render: overlay` 的项。
- 框要稍大于文字（四周留 5–10 像素），框边缘不要压在插画元素或色块边上，否则抹平后会留下一条色带；先看首帧再定稿。
- 抹平只适合文字落在平整底色或渐变底上的图；文字压在复杂插画上的标签不要选。

## 输出格式与子类

`--format gif|webp`，缺省按输出后缀。WebP 用有损编码，体积通常是 GIF 的一半以下，网页展示用；GIF 用于公众号、微信、X 这些不支持动画 WebP 的出口。`--target web` 是网页展示口径（长边 640、≤1.5MB）；`--target web-small` 给表情包的网页版（长边 320、≤400KB）。`--color` 可改 glow、particles 的颜色：浅底图用默认的浅金色会看不见，要换深一点的颜色。

| 子类 | 推荐模板 | GIF 出口 | 说明 |
|---|---|---|---|
| 文章动态插图：信息图 | labels | wechat-article | 标题与步骤标签依次出现 |
| 文章动态插图：绘本 | glow、particles | wechat-article | 光晕或飘动的光点，只动一块区域 |
| 表情包 | breathe、particles | wechat-sticker | 居中裁方 240×240，≤500KB |
| X 动图（海报） | glow、particles | x | 灯光脉冲或飘动粒子 |

官网「动图」用途：每个画风的合同登记 `samples/mo.webp`（动画，原样复制，不缩略）和 `samples/mo-0.webp`（静态原图），topic 写成「动图·子类·动效」，详情里显示「静图 → 动图」对比。


## 不做

不把任何第三方看板项目的代码或模板引入（其许可证禁止商用），只借「局部动效」的思路；不为每张图单独编排整套动画。
