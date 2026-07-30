from rest_framework import generics
from .models import User
from .serializers import RegisterSerializer
from rest_framework.permissions import AllowAny

from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken

from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import CustomTokenObtainPairSerializer
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import User

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.http import JsonResponse


import secrets
import string

from django.core.mail import send_mail
from django.db import transaction


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"message": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.role == "admin")

class ApproveUserView(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        user.status = "active"
        user.save()
        return Response({"message": f"User {user.email} approved."})


@csrf_exempt
@require_GET
def FetchLoginDetail(request):
    data = list(User.objects.filter(status="pending").values("id", "username", "date_joined"))
    return JsonResponse({"status" : "ok", "data": data})


class SendTemporaryPasswordView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        if user.status != "active":
            return Response(
                {"detail": "Only active users can receive a temporary password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        temporary_password = "".join(
            secrets.choice(alphabet) for _ in range(20)
        )

        try:
            with transaction.atomic():
                user.set_password(temporary_password)
                user.save(update_fields=["password"])

                sent = send_mail(
                    subject="Your Sarala Engineering temporary password",
                    message=(
                        f"Hello {user.username},\n\n"
                        "Your temporary password is:\n\n"
                        f"{temporary_password}\n\n"
                        "Please keep this password confidential. "
                        "You will be able to change it soon."
                    ),
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=False,
                )

                if sent != 1:
                    raise RuntimeError("Email could not be sent.")

        except Exception:
            return Response(
                {"detail": "Password email could not be sent. The password was not changed."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {"message": f"A temporary password was sent to {user.email}."},
            status=status.HTTP_200_OK,
        )