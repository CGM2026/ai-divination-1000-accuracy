# 新实验模板：有牌预测

本模板为公开整理新写。你只得到公开背景、问题、期限、达成标准、原牌序及固定方法。逐例使用附带词典，写三张具体翻译，连成一句自然、果决的判断，再明确回答问题。不要添加题面未给的具体事实来冒充已知情况。没有固定过去/现在/未来牌位；花色和牌值不直接决定吉凶。

不给条件式双答案。作出会或不会的单一判断，用概率表示把握。只按当前题目指定的人、物、时间和数量判断。

仅输出JSON数组，每个公开id恰好一项。字段：id、version（2.0）、cards（原序）、prediction（整数0或1）、p_yes（0到1，>=0.5对应1）、answer、combined_sentence、translations。translations为三项数组，依次含card、suit_meaning、value_meaning、context_translation，均为非空文字。answer以“我判断会”或“我判断不会”开头。不要输出结局、反馈或correct字段。
