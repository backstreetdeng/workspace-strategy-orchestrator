"""
快速测试脚本 - 一键验证 intent_classifier
运行方式：python test_quick.py
"""
import sys
sys.path.insert(0, ".")

from intent_classifier import IntentClassifier

classifier = IntentClassifier()

# 标准测试用例
tests = [
    # (问题, 预期意图)
    ("10-15万紧凑型SUV未来发展趋势如何", "趋势分析"),
    ("比亚迪在20-30万纯电SUV市场的竞品分析", "竞品分析"),
    ("分析30-50万豪华SUV的用户画像", "画像分析"),
    ("2025年新能源补贴退坡政策解读", "政策解读"),
    ("15-20万插混车型有哪些市场机会", "机会识别"),
    ("特斯拉Model Y的竞争优势", "竞品分析"),
    ("买比亚迪还是特斯拉好", "竞品分析"),
    ("蔚来ES6用户群体分析", "画像分析"),
    ("最近三个月新能源销量趋势", "趋势分析"),
    ("帮我分析下当前市场", "综合分析"),
    # 新增测试用例
    ("现在买新能源车合适吗", "趋势分析"),
    ("现在买电车划算吗", "趋势分析"),
    ("纯电和插混哪个更值得买", "竞品分析"),
    ("什么时候入手最合适", "趋势分析"),
    ("比亚迪秦和海豹怎么选", "竞品分析"),
]

print("=" * 70)
print("intent_classifier 快速测试")
print("=" * 70)

correct = 0
for i, (question, expected) in enumerate(tests, 1):
    result = classifier.classify(question)
    is_correct = result.intent_type == expected
    status = "✅" if is_correct else "❌"

    if is_correct:
        correct += 1

    print(f"\n{status} [{i}] {question}")
    print(f"   预期：{expected}")
    print(f"   结果：{result.intent_type} (置信度：{result.confidence})")
    if result.price_range:
        print(f"   价格：{result.price_range}")
    if result.brands_mentioned:
        print(f"   品牌：{result.brands_mentioned}")

print("\n" + "=" * 70)
print(f"准确率：{correct}/{len(tests)} = {correct/len(tests)*100:.1f}%")
print("=" * 70)
