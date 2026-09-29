# 生图服务与报错

外部服务适配层实现：`scripts/stylebook/backends/`。当前 Codex 会话若提供内置生图工具，用户已指定优先用它；这一路径不需要配置 API Key，也不经过 `sb.py generate`。Claude 本身不能生图，只负责读参考图与验收。

## Codex 内置生图

1. 写清单，运行 `python3 scripts/sb.py compile 清单.json --json`。将输出的完整 `prompt` 原样交给内置生图工具，不在编译结果外另写画风提示词。
2. 按输出顺序传入每个 `references[].path`；没有参考图时不传。图中出现的旧题材只供画风参考，遵守编译提示词里的隔离说明。透明底格式要求工具输出透明背景，其余格式用不透明背景。
3. 保存生成图，用 `sb.py export` 和 `sb.py qa` 检查实际消费尺寸。多页任务先 `sb.py plan 计划.json --manifests 清单目录`，逐张按上面流程执行；第二页起把首张成图按 `style` 参考加入逐页清单，并设 `use_anchor: false`，再编译，避免旧锚点与首图同时影响画风。当前 `sb.py batch` 使用外部服务适配层，不能自动调用 Codex 会话内置工具。
4. 编译输出里的 `model: gpt-image-2` 只是提示词方言和尺寸规则；内置工具未公开底层模型 ID 时，记录为「Codex 内置生图，实际模型 ID 未提供」，不能声称使用了某个具体版本。内置调用也不写入外部适配层的 `logs/cost.jsonl`。

## 外部服务

| 服务 | 环境变量 | 默认模型 | 参考图 | 实测 |
|---|---|---|---|---|
| OpenAI 及兼容中转 | `OPENAI_API_KEY`、`OPENAI_BASE_URL` | gpt-image-2 | 支持 | 已实测 |
| 火山方舟 Seedream | `ARK_API_KEY` | doubao-seedream-4-0-250828 | 支持 | 待实测 |
| 阿里云百炼（万相 / Qwen-Image） | `DASHSCOPE_API_KEY` | qwen-image-plus | 支持 | 待实测 |
| Google Gemini | `GEMINI_API_KEY`（可选 `GOOGLE_BASE_URL`） | gemini-3.1-flash-image | 支持 | 待实测 |
| OpenRouter | `OPENROUTER_API_KEY` | google/gemini-3.1-flash-image | 支持 | 待实测 |

使用 `sb.py generate` / `batch` 时，选服务顺序：命令行 `--provider` > 配置文件 `~/.config/sansheng-stylebook/config.json` > 按上表顺序找第一个配好的。当前会话没有内置工具且外部服务都未配置时，用 `sb.py inbox` 把编译好的提示词写成「待出图清单」，用户拿去任何工具出图，再回来验收。

## 报错怎么处理

| 类型 | 表现 | 处理 |
|---|---|---|
| busy | 429、5xx、「系统繁忙」「无可用渠道」 | 自动指数退避重试；连续两次繁忙且配了备用模型就切过去（用中转的 gpt-image-2 会自动加同模型备用线路 `gpt-image-2-c`） |
| auth | 401 / 403 | 密钥无效或没权限：不重试，请用户检查密钥；测试矩阵遇到它会整轮停下 |
| verify | 403 且提到组织验证 | OpenAI 要求先完成组织验证：platform.openai.com → Settings → Organization → Verify |
| policy | 内容被拒 | 不重试，换一种描述 |
| network | 连不上 | 重试；仍不行检查网络或 `*_BASE_URL` |

每次请求（成功与失败）都记进 `logs/cost.jsonl`（可用 `STYLEBOOK_LOG_DIR` 改位置），含估算费用；日志里的密钥会被遮盖。
