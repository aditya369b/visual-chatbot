from django.conf.urls import url
from chat import views

urlpatterns = [
    url(r'^$', views.home, name='home'),
    url(r'^upload/', views.upload_image, name='upload'),
    url(r'^uploadCondition/', views.upload_image_condition, name='uploadcondition'),
    url(r'^api/home/',views.home, name='apihome'),
    url(r'^api/upload/',views.upload_image,name='apiupload'),
]
