"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: gpt_structure.py (注意：实际文件名是 test.py)
描述: 调用 OpenAI API 的封装函数。
"""
import json
import random
import openai
import time 

from utils import *
openai.api_key = openai_api_key

def ChatGPT_request(prompt): 
  """
  给定一个提示和 GPT 参数字典，向 OpenAI 服务器发出请求并返回响应。
  参数:
    prompt: 一个字符串提示
    gpt_parameter: 一个 Python 字典，其键指示参数名称，值指示参数值。
  返回:
    GPT-3 响应的字符串。
  """
  # 临时休眠()
  try: 
    completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo", 
    messages=[{"role": "user", "content": prompt}]
    )
    return completion["choices"][0]["message"]["content"]
  
  except: 
    print ("ChatGPT ERROR") # Error message, kept in English
    return "ChatGPT ERROR" # Error message, kept in English

prompt = """
---
角色1: Maria Lopez 正在攻读物理学位，并在 Twitch 上直播游戏以赚取额外收入。她几乎每天都去 Hobbs Cafe 学习和吃饭。
角色2: Klaus Mueller 正在撰写一篇关于中产阶级化对低收入社区影响的研究论文。

过去背景: 
138 分钟前，Maria Lopez 和 Klaus Mueller 已经在谈论 Klaus 提到的 Maria 的研究论文。此对话发生在那次谈话之后。

当前背景: Maria Lopez 正在上她的物理课（为下一堂课做准备）时，在 Oak Hill College 的图书馆看到 Klaus Mueller 正在写他的研究论文（撰写引言部分）。
Maria Lopez 正考虑与 Klaus Mueller 发起一次对话。
当前位置: library in Oak Hill College

(这是 Maria Lopez 心里想的：Maria Lopez 应该记得就 Klaus Mueller 对她研究论文的看法进行后续交流。除此之外，Maria Lopez 不一定更了解 Klaus Mueller) 

(这是 Klaus Mueller 心里想的：Klaus Mueller 应该记得问 Maria Lopez 关于她的研究论文，因为他提到这篇论文时她觉得很有趣。除此之外，Klaus Mueller 不一定更了解 Maria Lopez) 

这是他们的对话。

Maria Lopez: "
---
以上述提示为准，以 json 格式输出回应。输出应该是一个列表的列表，其中内部列表的形式为 ["<姓名>", "<话语>"]。在对话中输出多轮话语，直到对话自然结束。
输出 json 示例:
{"output": "[["Jane Doe", "Hi!"], ["John Doe", "Hello there!"] ... ]"}
"""

print (ChatGPT_request(prompt))












