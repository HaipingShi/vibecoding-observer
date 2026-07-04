# Consulting Output Examples

> These examples show how a downstream agent should respond after the user
> selects one `consulting_routes` entry from `.analysis-profile.json`.

## Consumption Rules

When the user chooses a route:

1. Restate the selected route title and cite 1-3 `why_this_route` signals.
2. Read `consulting_output.output_type` and use the matching artifact shape.
3. Use `consulting_output.sections` as the required section list.
4. Ask only the necessary `starter_questions`; skip questions when the profile
   and report already contain enough evidence.
5. End with a short check against `completion_criteria`.

Do not present a fixed menu when dynamic routes are available. Do not make the
advice personal to the skill author; it is for the current user running
VibeCoding Observer.

## Example: project_start_prompt

Selected route:

```json
{
  "title": "把项目目标转成可执行工程闭环",
  "why_this_route": [
    "diagnosis: 顶层目标存在但工程闭环缺失",
    "top_level_goal_without_engineering_loop=469"
  ],
  "consulting_output": {
    "output_type": "project_start_prompt",
    "sections": ["目标重写", "硬约束", "交付物", "验收标准", "停止条件"]
  }
}
```

Response shape:

```markdown
你选的是：把项目目标转成可执行工程闭环

为什么先做这个：
- diagnosis: 顶层目标存在但工程闭环缺失
- top_level_goal_without_engineering_loop=469

## 目标重写
把“先理解项目 / 继续推进”改成一个可验收目标：
<用一句话写清用户结果、工程对象、完成边界>

## 硬约束
- WRITE_SCOPE: <允许修改的文件/模块>
- FORBIDDEN_SCOPE: <禁止修改的文件/配置/业务事实>
- 不允许依赖聊天记忆判断项目状态，以仓库文件和测试为准。

## 交付物
- <代码/文档/诊断报告/任务包>

## 验收标准
- <命令或人工验收步骤>
- <必须看到的结果>

## 停止条件
- 如果发现 IR/schema/依赖变化，停止并要求重新定界。
- 如果连续两次验证失败，先输出诊断而不是继续 patch。

完成检查：
- 目标能拆成 3-7 个可验收任务。
- 每个任务都有禁止范围和验证方式。
- agent 动手前能复述目标、约束和 Definition of Done。
```

## Example: task_prompt_template

Selected route:

```json
{
  "title": "重写任务入口提示词和交付协议",
  "why_this_route": [
    "diagnosis: 任务入口目标质量偏弱",
    "weak_goal=331"
  ],
  "consulting_output": {
    "output_type": "task_prompt_template",
    "sections": ["任务背景", "目标", "允许修改范围", "禁止范围", "验证命令", "交付格式"]
  }
}
```

Response shape:

````markdown
你选的是：重写任务入口提示词和交付协议

为什么先做这个：
- diagnosis: 任务入口目标质量偏弱
- weak_goal=331

## 任务背景
<给 agent 的必要事实，不放无关聊天历史>

## 目标
请完成 <一个具体工程目标>，完成后必须能通过 <验收证据> 证明。

## 允许修改范围
- <path/module>

## 禁止范围
- 不修改 <config/schema/lockfile/无关模块>
- 不主动新增依赖。

## 验证命令
```bash
<test command>
```

## 交付格式
最终回复必须包含：
1. 修改文件列表
2. 实现内容
3. 未完成项
4. 风险点
5. 测试 / 构建结果
6. 是否存在越界修改
7. 下一步建议
````

## Example: mid_project_recovery_plan

Selected route:

```json
{
  "title": "恢复项目方向和控制",
  "why_this_route": [
    "episode_signal: top_level_goal_without_engineering_loop=12"
  ],
  "consulting_output": {
    "output_type": "mid_project_recovery_plan",
    "sections": ["当前事实", "失控信号", "重新定界", "下一步任务包", "验证/停损点"]
  }
}
```

Response shape:

```markdown
你选的是：恢复项目方向和控制

## 当前事实
- 已完成：<从仓库文件、任务文档、git diff 中提取>
- 未验证：<没有证据的部分>
- 不确定：<需要用户或代码证据确认的部分>

## 失控信号
- <引用 why_this_route 和 episode_summary>

## 重新定界
- 当前目标：<一句话>
- 本轮只处理：<最小安全范围>
- 本轮不处理：<显式排除项>

## 下一步任务包
- Task ID: <T-XXX>
- WRITE_SCOPE:
- FORBIDDEN_SCOPE:
- Acceptance:
- Harness:

## 验证/停损点
- 通过：<命令/检查>
- 停止：<触发重新定界的条件>
```

## Example: architecture_level_review

Selected route:

```json
{
  "title": "做任务前抽象层级判断",
  "why_this_route": [
    "label: degen-wrong-layer=17"
  ],
  "consulting_output": {
    "output_type": "architecture_level_review",
    "sections": ["问题层级", "证据层", "推理层", "实现层", "验证层"]
  }
}
```

Response shape:

```markdown
你选的是：做任务前抽象层级判断

## 问题层级
这不是直接实现问题，先判断它属于：
- UI / 状态 / API / 数据模型 / 架构 / 流程 / 诊断

结论：<层级判断>

## 证据层
- 已读证据：<文件/报告/片段>
- 缺失证据：<需要再读什么>

## 推理层
- 人类会如何判断这个问题？
- 哪些低层 patch 会掩盖高层问题？

## 实现层
- 如果证据充足，最小实现范围是：<scope>
- 如果证据不足，先做：<read/review/probe>

## 验证层
- 用什么证明层级判断正确？
- 用什么证明实现没有越层？
```

## Example: agent_instructions_snippet

Selected route:

```json
{
  "title": "建立项目 AI 协作约束",
  "why_this_route": [
    "constraint_maturity=0.3"
  ],
  "consulting_output": {
    "output_type": "agent_instructions_snippet",
    "sections": ["默认工作方式", "写入范围", "禁止范围", "测试要求", "交付格式"]
  }
}
```

Response shape:

```markdown
你选的是：建立项目 AI 协作约束

下面是可放入 AGENTS.md / CLAUDE.md 的片段：

## 默认工作方式
- 先理解任务边界，再修改文件。
- 项目状态以仓库文件、任务文件、handoff 文件和 git diff 为准。
- 保持最小 diff，不做无关重构。

## 写入范围
- <允许 agent 修改的目录/文件>

## 禁止范围
- 不修改 lockfile、全局配置、schema，除非任务明确授权。
- 不覆盖其他 agent 或用户的未提交变更。

## 测试要求
- 修改代码后至少运行：<command>
- 无法运行时必须说明原因和风险。

## 交付格式
最终回复必须包含修改文件、实现内容、未完成项、风险、测试结果、越界检查和下一步建议。
```
