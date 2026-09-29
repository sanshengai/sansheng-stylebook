# 首次配置

目标：从安装到出第一张图只确认一次，**密钥不经过对话**。

1. 跑 `python3 scripts/sb.py doctor`，看各家「已配置 / 能连通 / 能出图 / 实测过」。
2. 没有任何一家配好时，跑 `python3 scripts/sb.py setup` 看菜单（国内用户优先：OpenAI 兼容中转、火山方舟、阿里云百炼；其次 Gemini、OpenRouter；第 6 项是不配服务、只用收件箱）。每家都附申请地址。
3. 请用户**自己**把密钥写进环境变量，或跑 `python3 scripts/sb.py setup --env-template` 生成 `~/.config/sansheng-stylebook/.env` 模板（权限 600）后自己填。明确告诉用户：不要把密钥发到对话里。
4. 用户填好后：`python3 scripts/sb.py setup --provider openai --model gpt-image-2`。它会先用最低成本出一张 1024² 低质量测试图，成功才保存；配置文件只存服务、模型、质量，不存密钥。
5. `python3 scripts/sb.py doctor --deep` 复核。

常见问题：401 = 密钥错或过期；403 提到组织验证 = 去 OpenAI 后台完成验证；连不上 = 检查 `OPENAI_BASE_URL` 是否带 `/v1`。
