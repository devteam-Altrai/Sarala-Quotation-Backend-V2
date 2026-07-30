from rest_framework import serializers
from .models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password]
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'role')

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data.get('username', ''),
            email=validated_data['email'],
            role=validated_data.get('role', 'employee'),
            status='pending'  # new users start as pending
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)

        if self.user.status != "active":
            raise serializers.ValidationError(
                {"detail": "Please contact administrator for access."}
            )

        # Optional: include username and role in the response
        data['id'] = self.user.id
        data['username'] = self.user.username
        data['role'] = self.user.role

        return data