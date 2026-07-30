from django.urls import path
from . import views
from .views import RegisterView, LogoutView, CustomLoginView, ApproveUserView, SendTemporaryPasswordView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomLoginView.as_view(), name="login"),  # replaced
    path('token/refresh/', TokenRefreshView.as_view(), name="token_refresh"),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('approve/<int:user_id>/', ApproveUserView.as_view(), name="approve_user"),  # new
    path('login-requests/', views.FetchLoginDetail, name="FetchLoginDetail"),
    path('users/<int:user_id>/send-temporary-password/',SendTemporaryPasswordView.as_view(),name='send_temporary_password'),
]