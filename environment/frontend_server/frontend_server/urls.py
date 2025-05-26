"""frontend_server URL 配置

`urlpatterns` 列表将 URL 路由到视图。更多信息请参见：
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
示例:
函数视图
    1. 添加导入: from my_app import views
    2. 向 urlpatterns 添加一个 URL: path('', views.home, name='home')
基于类的视图
    1. 添加导入: from other_app.views import Home
    2. 向 urlpatterns 添加一个 URL: path('', Home.as_view(), name='home')
包含另一个 URLconf
    1. 导入 include() 函数: from django.urls import include, path
    2. 向 urlpatterns 添加一个 URL: path('blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.urls import path
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static

from translator import views as translator_views

urlpatterns = [
    url(r'^$', translator_views.landing, name='landing'),
    url(r'^simulator_home$', translator_views.home, name='home'),
    url(r'^demo/(?P<sim_code>[\w-]+)/(?P<step>[\w-]+)/(?P<play_speed>[\w-]+)/$', translator_views.demo, name='demo'),
    url(r'^replay/(?P<sim_code>[\w-]+)/(?P<step>[\w-]+)/$', translator_views.replay, name='replay'),
    url(r'^replay_persona_state/(?P<sim_code>[\w-]+)/(?P<step>[\w-]+)/(?P<persona_name>[\w-]+)/$', translator_views.replay_persona_state, name='replay_persona_state'),
    url(r'^process_environment/$', translator_views.process_environment, name='process_environment'),
    url(r'^update_environment/$', translator_views.update_environment, name='update_environment'),
    url(r'^path_tester/$', translator_views.path_tester, name='path_tester'),
    url(r'^path_tester_update/$', translator_views.path_tester_update, name='path_tester_update'),
    path('admin/', admin.site.urls),
]
