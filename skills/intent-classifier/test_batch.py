# test_batch.py
import sys
sys.path.insert(0, ".")

from intent_classifier import IntentClassifier

classifier = IntentClassifier()

# 标准测试集（已知正确答案）
test_cases = [
    {
        "question": "10-15万紧凑型SUV未来发展趋势如何",
        "expected": "趋势分析"
    },
    {
        "question": "比亚迪在20-30万纯电SUV市场的竞品分析",
        "expected": "竞品分析"
    },
    {
        "question": "分析30-50万豪华SUV的用户画像",
        "expected": "画像分析"
    },
    {
        "question": "2025年新能源补贴退坡政策解读",
        "expected": "政策解读"
    },
    {
        "question": "15-20万插混车型有哪些市场机会",
        "expected": "机会识别"
    },
    {
        "question": "特斯拉Model Y的竞争优势",
        "expected": "竞品分析"
    },
    {
        "question": "纯电和插混哪个更值得买",
        "expected": "竞品分析"
    },
    {
        "question": "现在买新能源车合适吗",
        "expected": "时机判断"
    },
    # ========== 新增测试集（20道）==========
    {
        "question": "比亚迪和特斯拉哪个更值得买",
        "expected": "竞品分析"
    },
    {
        "question": "新能源车市场未来5年发展趋势预测",
        "expected": "趋势分析"
    },
    {
        "question": "25-30万区间有什么好的SUV推荐",
        "expected": "机会识别"
    },
    {
        "question": "分析小鹏汽车的主要用户群体特征",
        "expected": "画像分析"
    },
    {
        "question": "2025年北京上海新能源牌照政策会有什么变化",
        "expected": "政策解读"
    },
    {
        "question": "等电池成本下降后再买车划算吗",
        "expected": "时机判断"
    },
    {
        "question": "蔚来ES6和理想L7该怎么选",
        "expected": "竞品分析"
    },
    {
        "question": "工薪阶层买什么价位的电动车性价比最高",
        "expected": "画像分析"
    },
    {
        "question": "国产新能源车和合资品牌有什么差距",
        "expected": "竞品分析"
    },
    {
        "question": "双积分政策对车企有什么影响",
        "expected": "政策解读"
    },
    {
        "question": "年轻人买第一辆车该怎么选",
        "expected": "画像分析"
    },
    {
        "question": "电动车什么时候会取代燃油车",
        "expected": "趋势分析"
    },
    {
        "question": "增程式和插混哪个更适合跑长途",
        "expected": "竞品分析"
    },
    {
        "question": "购置税减免政策还有吗",
        "expected": "政策解读"
    },
    {
        "question": "买特斯拉还是等小米SU7",
        "expected": "竞品分析"
    },
    {
        "question": "中高端MPV市场有什么机会",
        "expected": "机会识别"
    },
    {
        "question": "退休老人买什么电动车代步好",
        "expected": "画像分析"
    },
    {
        "question": "纯电动车的续航里程以后能突破1000公里吗",
        "expected": "趋势分析"
    },
    {
        "question": "帮我分析下当前汽车市场",
        "expected": "综合分析"
    },
    {
        "question": "20万以内有哪些性价比高的选择",
        "expected": "机会识别"
    },
    {
        "question": "听说充电桩要涨价了是吗",
        "expected": "时机判断"
    },
    {
        "question": "比亚迪秦Plus和驱逐舰05有什么不同",
        "expected": "竞品分析"
    },
    {
        "question": "女生开什么车比较合适",
        "expected": "画像分析"
    },
    {
        "question": "充电桩建设政策对行业发展有何影响",
        "expected": "政策解读"
    },
    {
        "question": "今年车市价格战还会继续吗",
        "expected": "趋势分析"
    },
    {
        "question": "家庭第二辆车选纯电还是混动好",
        "expected": "竞品分析"
    },
    {
        "question": "15万落地预算买SUV，有什么推荐",
        "expected": "机会识别"
    }
]

# 运行测试
print("=" * 70)
print("批量测试结果")
print("=" * 70)

correct = 0
for i, case in enumerate(test_cases, 1):
    result = classifier.classify(case["question"])
    is_correct = result.intent_type == case["expected"]
    status = "✅" if is_correct else "❌"
    
    if is_correct:
        correct += 1
    
    print(f"\n{status} 测试{i}：{case['question']}")
    print(f"   预期：{case['expected']}")
    print(f"   实际：{result.intent_type} (置信度：{result.confidence})")

print("\n" + "=" * 70)
print(f"准确率：{correct}/{len(test_cases)} = {correct/len(test_cases)*100:.1f}%")