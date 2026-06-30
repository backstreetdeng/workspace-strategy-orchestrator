"""
汽车市场分析意图分类器 - LLM 版本

功能：
1. 使用 LLM 进行意图分类（语义理解）
2. Python 提取结构化维度（品牌、价格等）

使用方式：
    from intent_classifier import IntentClassifier

    classifier = IntentClassifier()
    result = classifier.classify("10-15万紧凑型SUV未来发展趋势如何")
    print(result)
"""

import re
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


def load_env():
    """加载 .env 文件"""
    # 优先从环境变量读取，如果已经设置则跳过
    if os.environ.get("MINIMAX_API_KEY"):
        return

    # 尝试多个可能的 .env 路径
    possible_paths = [
        # 当前项目根目录
        Path("E:/AI/data/envs/car_agent_env/.env"),
        # 用户目录
        Path.home() / ".env",
        # 当前工作目录
        Path(".env")
    ]

    for env_path in possible_paths:
        if env_path.exists():
            try:
                with open(env_path, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            os.environ[key] = value.strip()
                print(f"已加载环境配置: {env_path}")
                break
            except Exception as e:
                print(f"加载 {env_path} 失败: {e}")


# 初始化时加载 .env
load_env()


@dataclass
class IntentResult:
    """意图识别结果"""
    intent_type: str           # 意图类型
    confidence: float          # 置信度 0-1
    keywords: List[str]        # 提取的关键词
    dimensions: Dict[str, str] # 分析维度
    need_sentiment: bool       # 是否需要舆情
    analysis_depth: str        # 分析深度
    time_range: str           # 时间范围
    brands_mentioned: List[str] # 提到的品牌
    price_range: Optional[str] # 价格区间
    vehicle_type: Optional[str] # 车型类型
    power_type: Optional[str]  # 动力类型

    def to_dict(self) -> Dict:
        return asdict(self)


# LLM 提示词 - Ollama chat API 版本
OLLAMA_SYSTEM_PROMPT = """你是一个汽车市场分析意图分类器。输出JSON格式。只输出JSON，不要其他文字。
格式：{"intent_type":"意图","confidence":0.9,"dimensions":{"price":"","level":"","power":""},"need_sentiment":true}
意图可选：时机判断|趋势分析|画像分析|竞品分析|机会识别|政策解读|综合分析
优先级规则：1.包含"合适吗/值得买吗/划算吗/什么时候买/现在买"→时机判断 2.包含"趋势/走势/前景"→趋势分析"""

# MiniMax 版本提示词
MINIMAX_PROMPT = """你是一个汽车市场分析意图分类器。

分析用户问题，输出JSON格式结果。不要有其他解释文字。

用户问题：{0}

可选的意图类型：
- 时机判断：询问购车最佳时机，包括"合适吗/值得买吗/划算吗/什么时候买/现在买/降价/涨价/等一等/等降价"等
- 趋势分析：研究市场发展方向，包括"趋势/走势/前景/未来/取代/突破"等
- 画像分析：研究目标用户，包括"用户画像/消费者特征/购车偏好/什么样的人/哪类人/年轻人/老人/女生/工薪阶层"等描述特定用户群体的问题
- 竞品分析：比较产品/品牌/技术路线，包括"对比/竞品/哪个好/还是/有什么不同/竞争优势/怎么选/该如何选"等
- 机会识别：识别市场机会，包括"推荐/机会/切入点/空白/有哪些/性价比"等，特别是询问"有什么好的选择/推荐"的
- 政策解读：解读政策影响，包括"政策/补贴/购置税/退坡/双积分/牌照"等
- 综合分析：以上都不匹配时的默认分类

优先级规则（按顺序检查）：
1. 如果包含"值得买/划算吗/合适吗/现在买/什么时候买/降价/涨价/等降价"等直接询问购车时机 → 时机判断
2. 如果提到"XX岁/年轻人/老人/女生/工薪阶层/家庭"等具体用户群体询问"买什么好/怎么选/合适吗" → 画像分析
3. 如果问题同时提到两个具体品牌或产品（如"比亚迪和特斯拉"、"特斯拉还是小米SU7"）→竞品分析
4. 如果问题是"XX还是YY好/怎么选/该如何选"结构（技术路线对比如"纯电还是混动"） → 竞品分析
5. 如果包含"趋势/前景/未来/走势/取代/突破" → 趋势分析
6. 如果包含"政策/补贴/购置税/退坡/双积分/牌照" → 政策解读
7. 如果包含"推荐/有什么好的/有哪些性价比/有什么机会/有哪些选择"且没有特定用户群体 → 机会识别
8. 其他默认综合分析

输出格式（必须是这个格式，不能改变字段名）：
{{
  "intent_type": "意图类型",
  "confidence": 0.9,
  "dimensions": {{
    "价格区间": "",
    "车型级别": "",
    "动力类型": ""
  }},
  "need_sentiment": true
}}

只输出JSON，不要其他内容。
"""


class IntentClassifier:
    """汽车市场分析意图分类器（LLM版本）"""

    # 品牌识别（Python辅助）
    BRAND_PATTERNS = {
        "零跑": [r"零跑", r"C\d+", r"T03"],
        "比亚迪": [r"比亚迪", r"秦.*EV", r"汉.*EV", r"唐.*EV", r"宋.*EV", r"海豹", r"海狮", r"海鸥"],
        "特斯拉": [r"特斯拉", r"Tesla", r"Model\s*[3SYX]", r"model\s*[3syx]"],
        "问界": [r"问界", r"aito", r"M5", r"M7", r"M8"],
        "理想": [r"理想", r"Li\s*Auto", r"ONE", r"L6", r"L7", r"L8", r"L9"],
        "蔚来": [r"蔚来", r"NIO", r"ET[57]", r"ES[678]", r"EC[67]"],
        "小鹏": [r"小鹏", r"XPENG", r"G6", r"G9", r"P7", r"P5"],
        "小米": [r"小米", r"SU7", r"Xiaomi"],
        "吉利": [r"吉利", r"几何", r"极氪", r"领克"],
        "长安": [r"长安", r"深蓝", r"阿维塔"],
        "长城": [r"长城", r"魏牌", r"坦克", r"欧拉"],
        "上汽": [r"上汽", r"荣威", r"名爵", r"智己", r"飞凡"],
        "广汽": [r"广汽", r"埃安", r"传祺", r"昊铂"],
        "奇瑞": [r"奇瑞", r"星途", r"捷途", r"iCAR"],
        "大众": [r"大众", r"VW", r"ID\.[34]", r"帕萨特", r"迈腾"],
        "丰田": [r"丰田", r"TOYOTA", r"RAV4", r"凯美瑞", r"亚洲龙", r"bZ"],
        "本田": [r"本田", r"HONDA", r"CR-V", r"雅阁", r"皓影"],
        "宝马": [r"宝马", r"BMW", r"X[1-57]", r"3系", r"5系"],
        "奔驰": [r"奔驰", r"BENZ", r"Mercedes", r"C级", r"E级", r"GLC"],
        "奥迪": [r"奥迪", r"AUDI", r"A4", r"A6", r"Q5", r"Q3"]
    }

    # 舆情敏感意图（需要舆情辅助分析的意图类型）
    SENTIMENT_INTENTS = ["时机判断", "趋势分析", "画像分析", "竞品分析", "政策解读"]

    def __init__(self, use_llm: bool = True):
        """
        初始化分类器

        Args:
            use_llm: 是否使用 LLM 进行意图分类（默认True）
        """
        self.use_llm = use_llm
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则表达式"""
        self._compiled_brands = {k: [re.compile(p, re.IGNORECASE) for p in v]
                                  for k, v in self.BRAND_PATTERNS.items()}

    def classify(self, question: str) -> IntentResult:
        """
        分类用户问题

        Args:
            question: 用户输入的问题

        Returns:
            IntentResult: 结构化的分类结果
        """
        if not question or not question.strip():
            return self._default_result()

        if self.use_llm:
            # 优先使用 LLM 进行意图分类
            llm_result = self._classify_with_llm(question)
            if llm_result:
                # 补充 Python 提取的实体信息
                brands = self._extract_brands(question)
                dimensions = llm_result.get("dimensions", {})

                return IntentResult(
                    intent_type=llm_result["intent_type"],
                    confidence=llm_result["confidence"],
                    keywords=self._extract_keywords(question),
                    dimensions=dimensions,
                    need_sentiment=llm_result.get("need_sentiment", llm_result["intent_type"] in self.SENTIMENT_INTENTS),
                    analysis_depth="standard",
                    time_range=llm_result.get("time_range", "最近12个月"),
                    brands_mentioned=brands,
                    price_range=dimensions.get("价格区间"),
                    vehicle_type=dimensions.get("车型级别"),
                    power_type=dimensions.get("动力类型")
                )

        # LLM 失败时回退到规则匹配
        return self._classify_with_rules(question)

    def _classify_with_llm(self, question: str) -> Optional[Dict]:
        """
        使用 LLM 进行意图分类

        支持的 LLM：
        1. MiniMax API（优先）
        2. OpenAI API
        3. Ollama 本地模型

        Args:
            question: 用户问题

        Returns:
            Dict: LLM 返回的分类结果
        """
        import os
        import requests

        # 1. 尝试 MiniMax API
        try:
            minimax_api_key = os.environ.get("MINIMAX_API_KEY")
            minimax_group_id = os.environ.get("MINIMAX_GROUP_ID")

            if minimax_api_key and minimax_group_id:
                print("使用 MiniMax API...")
                response = requests.post(
                    "https://api.minimax.chat/v1/text/chatcompletion_v2",
                    headers={
                        "Authorization": f"Bearer {minimax_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "MiniMax-Text-01",
                        "messages": [
                            {"role": "user", "content": MINIMAX_PROMPT.format(question)}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 500
                    },
                    timeout=60
                )

                # 检查响应状态
                if response.status_code != 200:
                    print(f"MiniMax API 错误: {response.status_code} - {response.text[:200]}")
                else:
                    result = response.json()
                    llm_response = result["choices"][0]["message"]["content"]
                    print(f"MiniMax 响应: {llm_response[:150]}...")
                    parsed = self._parse_llm_response(llm_response)
                    print(f"解析结果: {parsed}")
                    if parsed:
                        return parsed
                    else:
                        print("MiniMax 响应解析失败，将使用规则版本")

        except Exception as e:
            print(f"MiniMax API 调用失败: {e}")
            import traceback
            traceback.print_exc()

        # 2. 尝试 OpenAI API
        try:
            import openai
            api_key = os.environ.get("OPENAI_API_KEY")
            if api_key:
                print("使用 OpenAI API...")
                client = openai.OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": INTENT_CLASSIFICATION_PROMPT.format(question=question)}],
                    temperature=0.1,
                    max_tokens=500
                )
                llm_response = response.choices[0].message.content
                return self._parse_llm_response(llm_response)
        except Exception as e:
            print(f"OpenAI API 调用失败: {e}")

        # 3. 尝试 Ollama 本地模型（chat API）
        try:
            print("使用 Ollama 本地模型 (chat API)...")
            ollama_url = "http://192.168.3.146:11434/api/chat"
            payload = {
                "model": "qwen2.5:14b-instruct",
                "messages": [
                    {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                    {"role": "user", "content": question}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.01,
                    "num_predict": 200
                }
            }
            response = requests.post(ollama_url, json=payload, timeout=120)
            response.raise_for_status()
            llm_response = response.json()["message"]["content"]
            print(f"Ollama 响应: {llm_response[:100]}...")

            # 解析响应
            parsed = self._parse_llm_response(llm_response)
            if parsed:
                print(f"Ollama 解析成功: {parsed.get('intent_type')}")
                return parsed

            # 如果解析失败，尝试从响应中提取意图
            return self._fallback_parse(question, llm_response)

        except Exception as e:
            print(f"Ollama API 调用失败: {e}")

        return None

    def _fallback_parse(self, question: str, response: str) -> Optional[Dict]:
        """
        当 LLM 没有返回标准 JSON 时的回退解析
        从响应文本中提取意图
        """
        try:
            response_lower = response.lower()
            question_lower = question.lower()

            # 意图判断（按优先级）
            # 1. 时机判断
            if any(kw in question_lower for kw in ["合适吗", "值得买", "划算吗", "什么时候买", "现在买", "等一等", "降价", "涨价"]):
                intent = "时机判断"
            # 2. 趋势分析
            elif any(kw in response_lower for kw in ["趋势", "趋势分析", "发展前景", "未来", "走势"]):
                intent = "趋势分析"
            # 3. 画像分析
            elif any(kw in response_lower for kw in ["画像", "用户画像", "消费者", "购车偏好"]):
                intent = "画像分析"
            # 4. 竞品分析
            elif any(kw in response_lower for kw in ["竞品", "竞争", "对比", "差异化"]):
                intent = "竞品分析"
            # 5. 机会识别
            elif any(kw in response_lower for kw in ["机会", "切入点", "空白", "蓝海"]):
                intent = "机会识别"
            # 6. 政策解读
            elif any(kw in response_lower for kw in ["政策", "补贴", "购置税", "退坡", "法规"]):
                intent = "政策解读"
            else:
                intent = "综合分析"

            # 提取维度
            dimensions = {}

            # 价格
            import re
            price_match = re.search(r'(\d+[-到至]\d+万)|(\d+万以[内外上下])', question)
            if price_match:
                dimensions["价格区间"] = price_match.group()

            # 级别
            for level in ["SUV", "MPV", "微型", "小型", "紧凑型", "中型", "中大型"]:
                if level in question:
                    dimensions["车型级别"] = level
                    break

            # 动力
            for power in ["纯电", "插混", "增程", "混动", "燃油"]:
                if power in question:
                    dimensions["动力类型"] = power
                    break

            return {
                "intent_type": intent,
                "confidence": 0.7,
                "dimensions": dimensions,
                "need_sentiment": intent in self.SENTIMENT_INTENTS
            }

        except Exception as e:
            print(f"回退解析失败: {e}")
            return None

    def _parse_llm_response(self, response: str) -> Optional[Dict]:
        """解析 LLM 返回的 JSON"""
        try:
            # 清理响应：移除代码块标记 ```json ``` 或 ```
            cleaned = response.strip()

            # 移除 ```json 和 ``` 标记
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned_lines = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped.startswith("```"):
                        cleaned_lines.append(line)
                cleaned = "\n".join(cleaned_lines).strip()

            # 尝试直接解析
            try:
                result = json.loads(cleaned)
                return result
            except json.JSONDecodeError:
                pass

            # 尝试提取 JSON 对象 { ... }
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    return result
                except json.JSONDecodeError:
                    pass

            # 尝试提取 JSON 数组 [ ... ]
            json_arr_match = re.search(r'\[[\s\S]*\]', cleaned)
            if json_arr_match:
                try:
                    result = json.loads(json_arr_match.group())
                    if isinstance(result, list) and len(result) > 0:
                        return result[0]
                except json.JSONDecodeError:
                    pass

            print(f"无法解析响应: {cleaned[:100]}...")
            return None

        except Exception as e:
            print(f"JSON 解析失败: {e}")
            print(f"原始响应: {response[:200]}...")
            return None

    def _classify_with_rules(self, question: str) -> IntentResult:
        """使用规则进行意图分类（备用方案）"""
        # 意图关键词（按优先级排序）
        intent_keywords = {
            "时机判断": ["合适吗", "值得买", "划算吗", "什么时候买", "现在买", "等一等", "降价", "涨价", "最佳时机", "购车时机"],
            "趋势分析": ["趋势", "发展前景", "未来", "走向", "预测", "走势", "发展趋势"],
            "画像分析": ["用户画像", "目标用户", "消费者画像", "购车偏好", "用户群体"],
            "竞品分析": ["竞品", "竞争对手", "对比", "哪个好", "还是", "差异化"],
            "机会识别": ["机会", "切入点", "空白", "蓝海", "增长点"],
            "政策解读": ["政策", "补贴", "购置税", "退坡", "法规", "双积分"]
        }

        # 匹配意图
        best_intent = "综合分析"
        max_score = 0

        for intent, keywords in intent_keywords.items():
            score = sum(1 for kw in keywords if kw in question)
            if score > max_score:
                max_score = score
                best_intent = intent

        confidence = min(0.9, 0.4 + max_score * 0.2) if max_score > 0 else 0.5

        # 提取维度
        dimensions = {}

        # 价格
        price_match = re.search(r'(\d+[-到至]\d+万)|(\d+万以[内外上下])', question)
        if price_match:
            dimensions["价格区间"] = price_match.group()

        # 级别
        for level in ["SUV", "MPV", "微型", "小型", "紧凑型", "中型", "中大型", "大型"]:
            if level in question:
                dimensions["车型级别"] = level
                break

        # 动力
        for power in ["纯电", "插混", "增程", "混动", "燃油"]:
            if power in question:
                dimensions["动力类型"] = power
                break

        return IntentResult(
            intent_type=best_intent,
            confidence=confidence,
            keywords=self._extract_keywords(question),
            dimensions=dimensions,
            need_sentiment=best_intent in self.SENTIMENT_INTENTS,
            analysis_depth="standard",
            time_range="最近12个月",
            brands_mentioned=self._extract_brands(question),
            price_range=dimensions.get("价格区间"),
            vehicle_type=dimensions.get("车型级别"),
            power_type=dimensions.get("动力类型")
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        keywords = []

        # 1. 提取品牌
        for brand, patterns in self._compiled_brands.items():
            for pattern in patterns:
                if pattern.search(text):
                    keywords.append(brand)
                    break

        # 2. 提取车型级别
        for level in ["SUV", "MPV", "微型车", "小型车", "紧凑型车", "中型车"]:
            if level in text:
                keywords.append(level)
                break

        # 3. 提取动力类型
        for power in ["纯电", "插混", "增程", "混动", "燃油"]:
            if power in text:
                keywords.append(power)
                break

        # 4. 提取价格
        price_match = re.search(r'(\d+[-到至]\d+万)|(\d+万以[内外上下])', text)
        if price_match:
            keywords.append(price_match.group())

        # 5. 提取意图相关词
        for word in ["趋势", "分析", "机会", "竞争", "用户", "政策"]:
            if word in text:
                keywords.append(word)

        return list(dict.fromkeys(keywords))[:8]

    def _extract_brands(self, text: str) -> List[str]:
        """提取品牌"""
        brands = []
        for brand, patterns in self._compiled_brands.items():
            for pattern in patterns:
                if pattern.search(text):
                    if brand not in brands:
                        brands.append(brand)
                    break
        return brands

    def _default_result(self) -> IntentResult:
        """默认结果"""
        return IntentResult(
            intent_type="综合分析",
            confidence=0.5,
            keywords=[],
            dimensions={},
            need_sentiment=False,
            analysis_depth="standard",
            time_range="最近12个月",
            brands_mentioned=[],
            price_range=None,
            vehicle_type=None,
            power_type=None
        )


# ============ 快捷调用函数 ============

def classify(question: str, use_llm: bool = True) -> Dict[str, Any]:
    """
    快捷分类函数

    Args:
        question: 用户问题
        use_llm: 是否使用 LLM（默认True）

    Returns:
        Dict: 分类结果字典
    """
    classifier = IntentClassifier(use_llm=use_llm)
    result = classifier.classify(question)
    return result.to_dict()


def skill_main(action: str, params: dict = None) -> dict:
    """
    OpenClaw skill 主入口

    Args:
        action: 操作类型 (classify)
        params: 参数字典

    Returns:
        标准化结果
    """
    if params is None:
        params = {}

    if action == "classify":
        question = params.get("question", "")
        return classify(question)
    else:
        return {"success": False, "error": f"未知操作: {action}"}


if __name__ == "__main__":
    # 测试示例
    test_cases = [
        "10-15万紧凑型SUV未来发展趋势如何",
        "比亚迪在20-30万纯电SUV市场的竞品分析",
        "分析30-50万豪华SUV的用户画像",
        "2025年新能源补贴退坡政策解读",
        "15-20万插混车型有哪些市场机会",
        "特斯拉Model Y的竞争优势",
        "现在买新能源车合适吗",
        "买比亚迪还是特斯拉好",
        "分析比亚迪"
    ]

    print("=" * 60)
    print("意图分类器测试（LLM版本）")
    print("=" * 60)

    classifier = IntentClassifier(use_llm=False)  # 默认先用规则测试

    for question in test_cases:
        print(f"\n输入：{question}")
        result = classifier.classify(question)
        print(f"  意图类型：{result.intent_type}")
        print(f"  置信度：{result.confidence}")
        print(f"  关键词：{result.keywords}")
        print(f"  分析维度：{result.dimensions}")
        print(f"  需要舆情：{result.need_sentiment}")
        if result.brands_mentioned:
            print(f"  品牌：{result.brands_mentioned}")
        print("-" * 60)
