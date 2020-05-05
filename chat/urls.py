from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns
from chat import views

urlpatterns = [
    url(r'^$', views.home, name='home'),
    url(r'^upload/', views.upload_image, name='upload'),
    url(r'^api_call/',views.api_call, name='api'),
    url(r'^api/home/',views.home, name='apihome'),
    url(r'^api/upload/',views.upload_image,name='apiupload'),
]
