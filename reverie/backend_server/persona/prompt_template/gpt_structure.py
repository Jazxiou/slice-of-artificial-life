"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: gpt_structure.py
描述: 调用 OpenAI API 的封装函数。
"""
import json
import random
import openai
import time 

from utils import *

openai.api_key = openai_api_key

def temp_sleep(seconds=0.1):
  time.sleep(seconds)

def ChatGPT_single_request(prompt): 
  temp_sleep()

  completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo", 
    messages=[{"role": "user", "content": prompt}]
  )
  return completion["choices"][0]["message"]["content"]


# ============================================================================
# #####################[第一节: CHATGPT-3 结构] ######################
# ============================================================================

def GPT4_request(prompt): 
  """
  给定一个提示和 GPT 参数字典，向 OpenAI 服务器发出请求并返回响应。
  参数:
    prompt: 一个字符串提示
    gpt_parameter: 一个 Python 字典，其键指示参数名称，值指示参数值。
  返回:
    GPT-3 响应的字符串。 (注：应为 GPT-4)
  """
  temp_sleep()

  try: 
    completion = openai.ChatCompletion.create(
    model="gpt-4", 
    messages=[{"role": "user", "content": prompt}]
    )
    return completion["choices"][0]["message"]["content"]
  
  except: 
    print ("ChatGPT ERROR") # Kept in English as an error identifier
    return "ChatGPT ERROR"  # Kept in English as an error identifier


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
    print ("ChatGPT ERROR")
    return "ChatGPT ERROR"


def GPT4_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  prompt = 'GPT-3 提示:\n"""\n' + prompt + '\n"""\n' # "GPT-3 Prompt:"
  prompt += f"请将对上述提示的回应以 json 格式输出。{special_instruction}\n" # "Output the response to the prompt above in json."
  prompt += "输出 json 示例:\n" # "Example output json:"
  prompt += '{"output": "' + str(example_output) + '"}' # "output" is a key, not translated.

  if verbose: 
    print ("CHAT GPT PROMPT") # DEBUG: "CHAT GPT PROMPT"
    print (prompt)

  for i in range(repeat): 

    try: 
      curr_gpt_response = GPT4_request(prompt).strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- 重试次数: \n", i, curr_gpt_response) # "---- repeat count: \n"
        print (curr_gpt_response)
        print ("~~~~") # Separator, not translated

    except: 
      pass

  return False


def ChatGPT_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  # prompt = 'GPT-3 提示:\n"""\n' + prompt + '\n"""\n' # "GPT-3 Prompt:"
  prompt = '"""\n' + prompt + '\n"""\n'
  prompt += f"请将对上述提示的回应以 json 格式输出。{special_instruction}\n" # "Output the response to the prompt above in json."
  prompt += "输出 json 示例:\n" # "Example output json:"
  prompt += '{"output": "' + str(example_output) + '"}' # "output" is a key, not translated.

  if verbose: 
    print ("CHAT GPT PROMPT") # DEBUG: "CHAT GPT PROMPT"
    print (prompt)

  for i in range(repeat): 

    try: 
      curr_gpt_response = ChatGPT_request(prompt).strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]

      # print ("---ashdfaf") # DEBUG
      # print (curr_gpt_response) # DEBUG
      # print ("000asdfhia") # DEBUG
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- 重试次数: \n", i, curr_gpt_response) # "---- repeat count: \n"
        print (curr_gpt_response)
        print ("~~~~") # Separator, not translated

    except: 
      pass

  return False


def ChatGPT_safe_generate_response_OLD(prompt, 
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  if verbose: 
    print ("CHAT GPT PROMPT") # DEBUG: "CHAT GPT PROMPT"
    print (prompt)

  for i in range(repeat): 
    try: 
      curr_gpt_response = ChatGPT_request(prompt).strip()
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      if verbose: 
        print (f"---- 重试次数: {i}") # "---- repeat count: "
        print (curr_gpt_response)
        print ("~~~~") # Separator, not translated

    except: 
      pass
  print ("FAIL SAFE TRIGGERED") # System status message, kept in English for potential grepping, or "故障安全已触发"
  return fail_safe_response


# ============================================================================
# ###################[第二节: 原始 GPT-3 结构] ###################
# ============================================================================

def GPT_request(prompt, gpt_parameter): 
  """
  给定一个提示和 GPT 参数字典，向 OpenAI 服务器发出请求并返回响应。
  参数:
    prompt: 一个字符串提示
    gpt_parameter: 一个 Python 字典，其键指示参数名称，值指示参数值。
  返回:
    GPT-3 响应的字符串。
  """
  temp_sleep()
  try: 
    response = openai.Completion.create(
                model=gpt_parameter["engine"],
                prompt=prompt,
                temperature=gpt_parameter["temperature"],
                max_tokens=gpt_parameter["max_tokens"],
                top_p=gpt_parameter["top_p"],
                frequency_penalty=gpt_parameter["frequency_penalty"],
                presence_penalty=gpt_parameter["presence_penalty"],
                stream=gpt_parameter["stream"],
                stop=gpt_parameter["stop"],)
    return response.choices[0].text
  except: 
    print ("TOKEN LIMIT EXCEEDED")
    return "TOKEN LIMIT EXCEEDED"


def generate_prompt(curr_input, prompt_lib_file): 
  """
  接收当前输入（例如，您想要分类的评论）和提示文件的路径。
  提示文件包含将使用的原始字符串提示，其中包含以下子字符串：!<INPUT>!
  ——此函数将此子字符串替换为实际的 curr_input，以生成将发送到 GPT-3 服务器的最终提示。
  参数:
    curr_input: 我们要输入的输入（如果多于一个输入，这可以是一个列表。）
    prompt_lib_file: 提示文件的路径。
  返回:
    将发送到 OpenAI GPT 服务器的字符串提示。
  """
  if type(curr_input) == type("string"): 
    curr_input = [curr_input]
  curr_input = [str(i) for i in curr_input]

  f = open(prompt_lib_file, "r")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):   
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt: 
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
  return prompt.strip()


def safe_generate_response(prompt, 
                           gpt_parameter,
                           repeat=5,
                           fail_safe_response="error",
                           func_validate=None,
                           func_clean_up=None,
                           verbose=False): 
  if verbose: 
    print (prompt)

  for i in range(repeat): 
    curr_gpt_response = GPT_request(prompt, gpt_parameter)
    if func_validate(curr_gpt_response, prompt=prompt): 
      return func_clean_up(curr_gpt_response, prompt=prompt)
    if verbose: 
      print ("---- repeat count: ", i, curr_gpt_response)
      print (curr_gpt_response)
      print ("~~~~")
  return fail_safe_response


def get_embedding(text, model="text-embedding-ada-002"):
  text = text.replace("\n", " ")
  if not text: 
    text = "此处为空白" # "this is blank"
  return openai.Embedding.create(
          input=[text], model=model)['data'][0]['embedding']


if __name__ == '__main__':
  gpt_parameter = {"engine": "text-davinci-003", "max_tokens": 50, 
                   "temperature": 0, "top_p": 1, "stream": False,
                   "frequency_penalty": 0, "presence_penalty": 0, 
                   "stop": ['"']}
  curr_input = ["driving to a friend's house"]
  prompt_lib_file = "prompt_template/test_prompt_July5.txt"
  prompt = generate_prompt(curr_input, prompt_lib_file)

  def __func_validate(gpt_response): 
    if len(gpt_response.strip()) <= 1:
      return False
    if len(gpt_response.strip().split(" ")) > 1: 
      return False
    return True
  def __func_clean_up(gpt_response):
    cleaned_response = gpt_response.strip()
    return cleaned_response

  output = safe_generate_response(prompt, 
                                 gpt_parameter,
                                 5,
                                 "rest",
                                 __func_validate,
                                 __func_clean_up,
                                 True)

  print (output)




















