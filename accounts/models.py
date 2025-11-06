from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.


class User(AbstractUser):
    ROLE_CHOICES = ( 
        ('admin', 'Admin'),
        ('employee', 'Employee'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')

     # make email unique and required
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'  # login with email instead of username
    REQUIRED_FIELDS = ['username']  # still keep username as extra field

    def __str__(self):
        return self.username