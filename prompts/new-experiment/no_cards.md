# 新实验模板：无牌预测

本模板为公开整理新写。只根据公开背景、问题、期限和达成标准判断。不抽牌，不调用牌义，不读取作者结局或其他预测。

逐例写具体理由，明确给出会或不会，用p_yes表示达成概率。不要用双方可能性包揽答案。

仅输出JSON数组，每个公开id恰好一项。字段：id、prediction（整数0或1）、p_yes（0到1，>=0.5对应1）、answer、rationale。answer和rationale均非空。不要输出cards、translations、combined_sentence、结局或correct字段。
