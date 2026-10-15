# 提示词与模型配置的来源

## 已恢复的历史材料

- `prompts/historical/phase2-controller.md`：第二轮中央总控任务书；含研究分工、随机规则和阶段安排。
- `prompts/historical/phase2-batches`：15份分组任务提示词；`archive/exploration-history`补存第一轮协议、阶段笔记、研究者报告与预试说明。
- `prompts/historical/evaluation-predictors.md`：千例预测工作说明；含两组读取范围、逐例写作与提交规则。
- `docs/historical/pilot-protocol.md`：百例试验约定。
- 冻结Skill及其引用文件：各阶段完整方法指令。

历史任务书明确指定第二轮总控使用`gpt-6-astra`、high，研究对话使用`gpt-6.1-sol`、medium。这是任务书中的指定配置；本包未据此声称每次实际调用都已核实同一模型。

原研究在Codex多对话上下文中进行，既有历史、调度消息和用户纠偏也是输入的一部分。部分调度消息无法从可见日志完整恢复。百例与千例每条预测的精确模型快照、采样参数、服务端种子没有逐次完备记录；这些项标为未恢复。详见来源审查。

## 本次新增的模板

`prompts/new-experiment`由本次公开整理新写，用于未来作者、有牌预测与无牌预测。它们保持实验角色和输出格式，采用可直接提交的JSON。文件不冒充历史逐字提示词。

`examples/model-config.example.json`是操作者填写的接口配置。工具为每次新调用保存请求模型、返回模型标识、温度、token上限、提示词哈希和响应内容哈希。API密钥不写入记录。

历史重算不调用模型。新的模板、种子模式与接口适配，不计为原实验的配置或新验证结果。
