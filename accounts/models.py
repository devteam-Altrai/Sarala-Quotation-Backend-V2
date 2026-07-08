from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('employee', 'Employee'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('rejected', 'Rejected'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    email = models.EmailField(unique=True)

    # NEW: status field for approval
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username