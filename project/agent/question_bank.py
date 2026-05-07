"""临床追问模板库：基于质量问题类型触发对应引导问题。"""

from __future__ import annotations

import random

RETAKE_QUESTIONS: dict[str, list[str]] = {
    "sharpness": [
        "图片有些模糊，麻烦稳住手或把手机放在稳定的地方重新拍一张？",
        "拍摄有点晃动，可以试试贴近对象放慢拍摄，清晰度会更好。",
    ],
    "brightness": [
        "图片偏暗，建议到光线充足的地方（靠近窗户或打开房灯）重拍一张。",
        "光线不够充分，能打开手机补光灯或者找更亮的环境拍摄吗？",
    ],
    "completeness": [
        "皮损区域好像没完全拍进去，麻烦往后退一点，把整个色斑/痣都拍在画面里。",
        "图片里只看到了部分皮损，请确保完整拍到整个患处区域。",
    ],
    "color_temp": [
        "图片色偏较明显，建议关闭美颜/滤镜，用标准相机模式在自然光下重拍。",
        "色温偏差影响分析，能换到自然光环境或关掉暖光灯重拍吗？",
    ],
    "contrast": [
        "对比度偏低，皮损边界不够清晰，建议换到光线均匀的环境重拍。",
        "皮损和周围皮肤区分不够明显，换个光线更均匀的角度拍摄会更好。",
    ],
}

CLINICAL_QUESTIONS: list[str] = [
    "这个皮损大概出现多久了？最近有没有明显变化（变大、颜色加深、形状改变等）？",
    "摸上去有没有瘙痒、疼痛或出血的感觉？",
    "家族里有没有皮肤癌或黑色素瘤的病史？",
    "这个部位是否经常受到阳光直射？",
]


def get_retake_question(issue: str) -> str:
    """根据质量问题类型，随机返回一条引导重拍的问题。"""
    options = RETAKE_QUESTIONS.get(issue, [f"图片质量（{issue}）不足，能重新拍一张吗？"])
    return random.choice(options)


def get_clinical_question(asked: list[str]) -> str | None:
    """返回一条尚未问过的临床问题，若都问过了则返回 None。"""
    for q in CLINICAL_QUESTIONS:
        if q not in asked:
            return q
    return None
