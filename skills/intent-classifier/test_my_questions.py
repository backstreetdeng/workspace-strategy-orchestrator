# 创建测试文件 test_my_questions.py
import sys
sys.path.insert(0, ".")

from intent_classifier import IntentClassifier

# 创建分类器
classifier = IntentClassifier()

# 测试你的问题
question = "比亚迪的市场战略"
result = classifier.classify(question)

# 打印完整结果
print(f"\n问题：{question}")
print(f"意图类型：{result.intent_type}")
print(f"置信度：{result.confidence}")
print(f"关键词：{result.keywords}")
print(f"分析维度：{result.dimensions}")
print(f"需要舆情：{result.need_sentiment}")
print(f"品牌：{result.brands_mentioned}")
print(f"价格区间：{result.price_range}")
print(f"车型：{result.vehicle_type}")
print(f"动力类型：{result.power_type}")