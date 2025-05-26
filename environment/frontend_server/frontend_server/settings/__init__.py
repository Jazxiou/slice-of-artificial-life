###用于将静态文件推送到 AWS



# from .base import *
# from .production import *

# try:
#   from .local import *
# except:
  # pass






###通用配置





from .base import *

try: 
  from .local import *
  live = False
except:
  live = True

if live:
  from .production import *
