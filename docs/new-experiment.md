# 新实验操作

全部命令在仓库根目录执行。每次使用一个新的运行目录；`runs/`默认由Git忽略。

## 手动方式

1. 按`examples/story.example.json`的字段写故事数组，先写定问题、二元标准和结局。
2. 固定一个方法目录，执行初始化和抽牌：

```bash
python lab.py init --root runs/new --stories runs/new-stories.json --count 10 --batch-size 5 --seed 20261015
python lab.py prepare --root runs/new
```

不填`--seed`则使用系统随机。原实验采用系统随机；种子是新工具的功能。每题轮内不放回抽三张，下一题恢复全52张。

3. 将`packets/cards`交有牌预测者，连同run内固定method；将`packets/no_cards`交无牌预测者。按`prompts/new-experiment`的JSON格式分别写预测数组。

```bash
python lab.py submit --root runs/new --arm cards --input runs/cards-0001.json
python lab.py submit --root runs/new --arm no_cards --input runs/base-0001.json
```

每批提交后继续其余批次。提交入口不揭晓结局，已提交答案禁止更换。

4. 独立审查者按每题的原标准核对结局，保存`id`、`status`、`reason`数组。status为pass、ambiguous或contradictory；需要替代标签时另填`alternative_outcome`。

```bash
python lab.py audit --root runs/new --input runs/new-audit.json
python lab.py seal --root runs/new
python lab.py score --root runs/new
python lab.py verify --root runs/new
```

两组全部提交并封存后才能评分。核验会检测冻结文件更改。

## 模型接口方式

接口需接受Chat Completions格式：POST完整endpoint，`model`、`messages`、`temperature`与`max_tokens`字段；响应文本放在`choices[0].message.content`中，内容为JSON数组。其他服务可自行适配这个契约。

复制`examples/model-config.example.json`到`runs/model-config.json`，填写服务地址和各角色模型，按其中`api_key_env`设置环境变量。不要把真实凭据填入文件。

```bash
python lab.py generate --config runs/model-config.json --count 10 --output runs/new-stories.json
```

先审查生成的故事，再按上文初始化和抽牌。每批分别调用：

```bash
python lab.py predict --root runs/new --arm cards --packet runs/new/packets/cards/0001-0005.json --config runs/model-config.json --output runs/cards-0001.json
python lab.py predict --root runs/new --arm no_cards --packet runs/new/packets/no_cards/0001-0005.json --config runs/model-config.json --output runs/base-0001.json
```

检查后提交上述输出，完成所有批次再封存评分。predict只向模型传该组公开题面；有牌组另传固定Skill与词典。每次API请求使用独立messages，不自动继承作者会话或另一组回答。程序会校验全目录的冻结哈希，权限隔离仍由操作者安排。

generate与predict会发出真实接口请求。离线`demo`和`reproduce`不发请求。接口元数据存于输出旁的`.metadata.json`，不包含密钥。
