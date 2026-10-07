# 本地偏好与逐渐适应

偏好保存在 `SANSHENG_IMAGE_PROFILE/memory.json`；未设置环境变量时使用 `~/.config/sansheng-image/profile/memory.json`。公开仓库和网页不读取这份本地文件。已有 `author.json` 保留原状，新的明确设置覆盖其默认；项目锁定和本次指定仍有更高优先级。

## 何时记录

| 用户行为 | 操作 | 会不会改变长期默认 |
|---|---|---|
| “以后公众号文章用 C31” | `preferences set --scene wxillus --field style --value C31` | 立即生效 |
| “以后公众号配图更柔和” | `preferences set --scene wxillus --field palette --value '{"family":"macaron","light":0,"sat":-1}'` | 立即生效 |
| “这张改成 C25” | 只修改本次计划中该图，`manual: true` | 不会 |
| 用户看过候选后主动改选 | `preferences record --scene wxillus --field style --value C31 --task <独立任务 ID> --candidates '["C08","C31"]'` | 同一场景、字段、范围的三个独立任务一致时形成观察倾向，只提高未锁定推荐 |
| 事实错误、漏字、自动 QA 返修、沉默 | 不记录审美事件 | 不会 |

`style`、`palette`、`form`、`structure` 都可记录。`--project <项目 ID>` 可以把设置限制在一个项目；同一场景和项目的证据不会混到另一个项目。宿主 Agent 把自然语言理解成具体字段和值后调用 CLI，不需用户手写这些命令。`palette` 保留色系、深浅、鲜灰；品牌色还需 `custom: ["#RRGGBB"]`。

## 查看与管理

```bash
python3 scripts/sb.py preferences show --scene wxillus
python3 scripts/sb.py style-for wxillus
python3 scripts/sb.py preferences clear --scene wxillus --field style
python3 scripts/sb.py preferences undo --event-id <事件 ID>
python3 scripts/sb.py preferences forget --event-id <事件 ID>
python3 scripts/sb.py preferences pause
python3 scripts/sb.py preferences resume
python3 scripts/sb.py preferences export --file <备份.json>
python3 scripts/sb.py preferences import --file <备份.json>
```

`clear` 让这个范围回到更低优先级的设置，留下可追溯事件。`undo` 撤销指定事件；`forget` 删除事件原值并保留不含原值的 ID 墓碑，重新导入旧备份也不会复活。导入遇到互相矛盾的明确设置会拒绝，确认后才能加 `--replace-conflicts`。`pause` 暂停记录及使用观察倾向，已有明确设置继续有效。文件写入采用锁和原子替换；同一事件 ID 重试不会重复累计。

本地画廊的“偏好”页可导入上述 `memory.json`，查看明确设定和观察证据，按场景/项目新增明确设定，清除设定、忘记来源、暂停观察学习，再下载文件交给 Agent 导入。页面只在打开期间持有导入的记忆文件，不自动写 Agent profile；浏览器里的去掉项和场景默认另存于浏览器，不代表长期偏好已经同步。画廊下载文件若带 `apply_paused: true`，`preferences import` 会应用其中的暂停状态；普通旧备份没有此字段，导入时不会改当前暂停状态。对已有范围设置不同值时，CLI 会显示冲突，核对后才可用 `--replace-conflicts`。不要将个人记忆文件打进公开画廊或仓库。

## 推荐解释与边界

`style-for` 的 `source` 会标明本次指定、项目锁定、明确偏好、观察倾向、作者档案或出厂默认；观察倾向带证据事件 ID。明确设置从不因使用次数自动过期。偏好文件损坏时，`style-for` 报告警告并退回作者档案或出厂默认。三次只是工程起点，不能因为模拟测试通过就宣称已从真实用户身上学到偏好。

记忆文件只存场景、项目 ID、字段改动、时间、任务 ID、实际展示的候选和短备注；不复制文章全文、聊天记录或图片。公开选择器只能导出选择配置，不能访问本地偏好文件。
