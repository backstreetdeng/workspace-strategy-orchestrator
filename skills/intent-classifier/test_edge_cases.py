# test_edge_cases.py
import sys
sys.path.insert(0, ".")

from intent_classifier import IntentClassifier

classifier = IntentClassifier()

# 边界测试用例
edge_cases = [
    "买比亚迪还是特斯拉",                    # 双品牌对比
    "最近三个月销量怎么样",                   # 时间范围
    "帮我分析下",                           # 模糊问题
    "20万以内性价比最高的车是哪款",          # 推荐需求
    "蔚来ES6和小鹏G9怎么选",               # 具体车型对比
    "2024年市场表现",                        # 年份指定
    "女生适合开什么车",                      # 画像特征
    "充电不方便买什么车",                    # 使用场景
]

print("边界测试")
print("-" * 70)

for question in edge_cases:
    result = classifier.classify(question)
    print(f"\n问题：{question}")
    print(f"  → {result.intent_type} (置信度：{result.confidence})")
    print(f"  维度：{result.dimensions}")
    print(f"  品牌：{result.brands_mentioned}")