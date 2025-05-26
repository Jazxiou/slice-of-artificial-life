"""
作者: Joon Sung Park (joonspk@stanford.edu)

文件: global_methods.py
描述: 包含在我的各个项目中使用的函数。
"""
import random
import string
import csv
import time
import datetime as dt
import pathlib
import os
import sys
import numpy
import math
import shutil, errno

from os import listdir

def create_folder_if_not_there(curr_path): 
  """
  检查 curr_path 中的文件夹是否存在。如果不存在，则创建该文件夹。
  请注意，如果 curr_path 指定的是文件位置，则它将操作包含该文件的文件夹。
  但即使用于仅指定文件夹的路径，此函数也同样有效。
  参数:
    curr_path: 当前路径
  返回:
    True: 如果创建了新文件夹
    False: 如果未创建新文件夹
  """
  outfolder_name = curr_path.split("/")
  if len(outfolder_name) != 1: 
    # 这会检查当前路径是文件还是文件夹。
    if "." in outfolder_name[-1]: 
      outfolder_name = outfolder_name[:-1]

    outfolder_name = "/".join(outfolder_name)
    if not os.path.exists(outfolder_name):
      os.makedirs(outfolder_name)
      return True

  return False 


def write_list_of_list_to_csv(curr_list_of_list, outfile):
  """
  将列表的列表写入 CSV 文件。
  与 write_list_to_csv_line 不同，它一次性写入整个 CSV 文件。
  参数:
    curr_list_of_list: 要写入的列表。列表格式如下：
               [['key1', 'val1-1', 'val1-2'...],
                ['key2', 'val2-1', 'val2-2'...],]
    outfile: 要写入的 CSV 文件的名称
  返回:
    无
  """
  create_folder_if_not_there(outfile)
  with open(outfile, "w") as f:
    writer = csv.writer(f)
    writer.writerows(curr_list_of_list)


def write_list_to_csv_line(line_list, outfile): 
  """
  将一行写入 CSV 文件。
  与 write_list_of_list_to_csv 不同，此函数会打开一个现有的输出文件，
  然后向该文件追加一行。
  如果文件尚不存在，此函数也同样有效。
  参数:
    line_list: 要写入的列表。列表格式如下：
               ['key1', 'val1-1', 'val1-2'...]
               重要的是，这不是列表的列表。
    outfile: 要写入的 CSV 文件的名称
  返回:
    无
  """
  create_folder_if_not_there(outfile)

  # 首先打开文件，以便我们可以随着进度增量写入
  curr_file = open(outfile, 'a',)
  csvfile_1 = csv.writer(curr_file)
  csvfile_1.writerow(line_list)
  curr_file.close()


def read_file_to_list(curr_file, header=False, strip_trail=True): 
  """
  将 CSV 文件读入列表的列表。如果 header 为 True，则返回一个包含 (标题行, 所有行) 的元组。
  参数:
    curr_file: 当前 CSV 文件的路径。
    header: 布尔值，指示文件是否包含标题行 (默认为 False)。
    strip_trail: 布尔值，指示是否去除每行末尾的空白字符 (默认为 True)。
  返回:
    列表的列表，其中内部列表是文件的行。如果 header 为 True，则返回 (标题行, 所有其他行)。
  """
  if not header: 
    analysis_list = []
    with open(curr_file) as f_analysis_file: 
      data_reader = csv.reader(f_analysis_file, delimiter=",")
      for count, row in enumerate(data_reader): 
        if strip_trail: 
          row = [i.strip() for i in row]
        analysis_list += [row]
    return analysis_list
  else: 
    analysis_list = []
    with open(curr_file) as f_analysis_file: 
      data_reader = csv.reader(f_analysis_file, delimiter=",")
      for count, row in enumerate(data_reader): 
        if strip_trail: 
          row = [i.strip() for i in row]
        analysis_list += [row]
    return analysis_list[0], analysis_list[1:]


def read_file_to_set(curr_file, col=0): 
  """
  将 CSV 文件的“单列”读入一个集合。
  参数:
    curr_file: 当前 CSV 文件的路径。
    col: 要读取的列的索引 (默认为 0)。
  返回:
    包含 CSV 文件单列中所有项的集合。
  """
  analysis_set = set()
  with open(curr_file) as f_analysis_file: 
    data_reader = csv.reader(f_analysis_file, delimiter=",")
    for count, row in enumerate(data_reader): 
      analysis_set.add(row[col])
  return analysis_set


def get_row_len(curr_file): 
  """
  获取 CSV 文件中的行数。
  参数:
    curr_file: 当前 CSV 文件的路径。
  返回:
    行数。
    如果文件不存在，则返回 False。
  """
  try: 
    analysis_set = set()
    with open(curr_file) as f_analysis_file: 
      data_reader = csv.reader(f_analysis_file, delimiter=",")
      for count, row in enumerate(data_reader): 
        analysis_set.add(row[0])
    return len(analysis_set)
  except: 
    return False


def check_if_file_exists(curr_file): 
  """
  检查文件是否存在。
  参数:
    curr_file: 当前文件的路径。
  返回:
    如果文件存在，则为 True。
    如果文件不存在，则为 False。
  """
  try: 
    with open(curr_file) as f_analysis_file: pass
    return True
  except: 
    return False


def find_filenames(path_to_dir, suffix=".csv"):
  """
  给定一个目录，查找所有以提供的后缀结尾的文件，并返回它们的路径。
  参数:
    path_to_dir: 当前目录的路径。
    suffix: 目标后缀 (默认为 ".csv")。
  返回:
    目录中所有匹配文件的路径列表。
  """
  filenames = listdir(path_to_dir)
  return [ path_to_dir+"/"+filename 
           for filename in filenames if filename.endswith( suffix ) ]


def average(list_of_val): 
  """
  计算列表中数字的平均值。
  参数:
    list_of_val: 一个数值列表。
  返回:
    这些值的平均值。
  """
  return sum(list_of_val)/float(len(list_of_val))


def std(list_of_val): 
  """
  计算列表中数字的标准差。
  参数:
    list_of_val: 一个数值列表。
  返回:
    这些值的标准差。
  """
  std = numpy.std(list_of_val)
  return std


def copyanything(src, dst):
  """
  将源文件夹中的所有内容复制到目标文件夹。
  参数:
    src: 源文件夹的地址。
    dst: 目标文件夹的地址。
  返回:
    无
  """
  try:
    shutil.copytree(src, dst)
  except OSError as exc: # python >2.5 版本
    if exc.errno in (errno.ENOTDIR, errno.EINVAL):
      shutil.copy(src, dst)
    else: raise


if __name__ == '__main__':
  pass
















