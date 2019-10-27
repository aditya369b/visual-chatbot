from django.conf.urls import url
from chat import views

urlpatterns = [
    url(r'^$', views.home, name='home'),
    url(r'^upload/', views.upload_image, name='upload'),
    url(r'^api_call/',views.api_call, name='api'),
]
