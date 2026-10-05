# 测试矩阵与准入（维护者）

矩阵 `state.json` 的每次 `reviews[]` 和 `report.md` 逐题记录看图来源：默认独立 CLI 为 `claude_cli`；设 `STYLEBOOK_QA_BACKEND=ark_agent_plan` 时使用现有 Agent Plan 套餐的豆包视觉，来源为 `ark_agent_plan`。两者各自的无历史上下文请求可计入独立双评；由调用者提供的结论须标明来源，未标明记作 `provided_unspecified`，旧缓存无来源记作 `legacy_unknown`，这些不能顶替独立双评。续跑沿用旧看图结论时不改写其来源；已有维护者自检也不能挡住补看独立结论。`admission.matrix_verdict` 只表示八题数量和指定题的自动判据；`admission.verdict` 是正式准入状态。即使前者为 `pass`，同词三次稳定及跨样式可区分仍须另附证据，后者保持 `pending`，不能凭八题数量把合同标为正式准入。来源标签不能代替检查原始看图记录。

## 8 道标准题

题目在 `tests/matrix/questions.json`（当前 v6）：T1 半身表情、T2 两人互动（用 T1 出图作角色参考）、T3 老人与孩子、T4 动物、T5 静物、T6 远景（16:9）、T7 抽象概念（含中文标签）、T8 3:4 中文标题卡。题目对样式保持中立：不指定颜色与材质，角色辨识靠发型、眼镜、发夹这类形状。v4 明确 T1 发夹位于人物自身左侧，并纳入验收条目；T1 和依赖其身份参考的 T2 旧分数不能沿用。v5 把 T7 验收中原有的“番茄计时器位于视觉中心”写进实际出图题面；旧 T7 图不能沿用。原生文字提示词也明确禁止未要求的步骤数字和道具刻度，受影响的文字题须按新编译词重出。v6 把 T2/T5 题面已有的人数与物件数量编进 `content.inventory`，并交独立看图核对；数量按主场景中的不同人物和物件计算，技术细节小窗重复展示同一实体不算新增。此前两题的出图词没有明示排除项，旧 T2/T5 分数不能沿用。改题要升 version，并重跑受影响的样式。

```bash
python3 scripts/sb.py matrix C31 --max-usd 1.0          # 出图 + 看图 + 判定 + 矩阵图与报告
python3 scripts/sb.py matrix C31 --only T7,T8            # 只跑几题
python3 scripts/sb.py matrix C31 --no-review             # 只出图（或只按新规则重算判定）
```

输出在 `out/matrix/<码>@r<修订>/`：每题的图、提示词、看图结论，`state.json`，`matrix.png`，`report.md`，`consistency-T1-T2.png`。
断点续跑：提示词没变且图还在就不重出；图和看图题目都没变、结论完整就不重看；判定每次按最新规则重算。
预算：`--max-usd` 是本轮新增花费上限。密钥无效、需要组织验证、没有服务时整轮停下。

## 准入线

8 题至少过 7；T3 必过；声称能直接写中文的（`text_mode` 含 native）T8 必过；同一提示词出 3 次风格一致；与已入库样式并排看不会混淆；配方里不出现在世画家与工作室名。**不过线就改配方或换掉，不降标准。** 前三条脚本自动判（报告「准入线」一节），后三条人工确认。看图结论有波动，准入时每题看两次，不一致交人复核。

边界缺陷可用 `sb.py qa-contrast` 对旧问题图与返修图做匿名、换序的**相对**比较；判据、原图哈希、两次判断须留档。裁局部时两图用同一裁切框，并保留全图。对照结论不能拼入八题矩阵，也不能代替每题独立双评、同词三次一致性或跨样式区分。

能力标签（`abilities`）只能来自实测：中文 ← T7、T8；角色一致 ← T2；儿童 ← T3；视频帧 ← T6；会不会给无人场景加人 ← T5。

## 样图入库与 samples 分支

主分支不跟踪 `styles/*/samples/`（已写入 `.gitignore`），样图放在同仓的孤儿分支 `samples`。入库脚本（`ingest*.py` 等）照旧把文件写进工作区的 `styles/<码>/samples/`，写完后：

```bash
python3 scripts/samples_sync.py push      # 工作区样图 → 本地 samples 分支（内容没变不产生新提交），输出提交 sha
python3 scripts/samples_sync.py status    # 对比工作区与分支头
# 再由维护者推送：git push origin samples
```

新克隆的维护者先 `git fetch origin samples:refs/remotes/origin/samples`，再 `python3 scripts/samples_sync.py pull` 取回样图。合同 `samples` 里登记的 `ratio` 要与文件一致——没有样图文件时，选择器按登记比例重建。锚点图（`styles/<码>/anchor.*`）与范例图（合同 `exemplars`）不得放进 `samples/`，它们随主分支分发。

## 注册表与画廊

```bash
python3 scripts/sb.py build                  # 重建公开 registry.json（只含 C 码）
python3 scripts/sb.py build --check          # 只检查 registry.json 是否与目录、合同一致
python3 scripts/sb.py build --private --gallery --samples 样图目录   # 叠加私有 profile，生成本地画廊
```

画廊是单文件 HTML（`gallery/build/`，不进仓库），三页：出厂默认、全部样式（可去掉不要的）、选择器（给出风格码、给 Skill 的一句话、完整提示词）。样图优先取测试矩阵出图，其次 `--samples` 目录里的 `<码>-T3.png`（旧名 `<码>-q1/q2/q3` 分别对应 T3/T6/T7）。
