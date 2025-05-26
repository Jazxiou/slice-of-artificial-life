"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: print_prompt.py
描述: 用于在详细模式设置为 True 时打印提示信息。
"""
import sys
sys.path.append('../')

import json
import numpy
import datetime
import random

from global_methods import *
from persona.prompt_template.gpt_structure import *
from utils import *

##############################################################################
#                    角色 第1章: 提示结构                    #
##############################################################################

def print_run_prompts(prompt_template=None, 
                      persona=None, 
                      gpt_param=None, 
                      prompt_input=None,
                      prompt=None, 
                      output=None): 
  print (f"=== {prompt_template}")
  print ("~~~ 角色    ---------------------------------------------------")
  print (persona.name, "\n")
  print ("~~~ gpt参数 ----------------------------------------------------")
  print (gpt_param, "\n")
  print ("~~~ 提示输入    ----------------------------------------------")
  print (prompt_input, "\n")
  print ("~~~ 提示    ----------------------------------------------------")
  print (prompt, "\n")
  print ("~~~ 输出    ----------------------------------------------------")
  print (output, "\n") 
  print ("=== 结束 ==========================================================")
  print ("\n\n\n")
