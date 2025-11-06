from django.db import models
from django.utils import timezone

# Create your models here.
class ProjectData(models.Model):
    project_name = models.CharField(max_length=255)  # e.g., ZIP file name
    part_no = models.CharField(max_length=255)
    description = models.TextField()
    mat = models.FloatField(null=True, blank=True)
    vmc = models.FloatField(null=True, blank=True)
    cnc = models.FloatField(null=True, blank=True)
    hand = models.FloatField(null=True, blank=True)
    laser = models.FloatField(null=True, blank=True)
    bend = models.FloatField(null=True, blank=True)
    weld = models.FloatField(null=True, blank=True)
    ext = models.FloatField(null=True, blank=True)
    quantity = models.IntegerField(default=0)
    profit = models.FloatField(null=True, blank=True)
    unit = models.FloatField(null=True, blank=True)
    total = models.FloatField(null=True, blank=True)
    # grand_total = models.FloatField(null=True, blank=True)
    # quotation_name = models.CharField(null =True,max_length=100)

    class Meta:
        unique_together = ('project_name', 'part_no')  # ensures overwriting, no duplicates

    def __str__(self):
        return f"{self.project_name} | {self.part_no} | {self.description}"


class Message(models.Model):
    text= models.CharField(max_length=100)

class DashboardData(models.Model):
    projectName = models.CharField(null=True, blank=True, max_length=100)
    quotationname = models.CharField(null=True, blank=True, max_length=100)
    grandTotal = models.FloatField(null=True, blank=True)
    
    # Automatically updated every time the record is saved
    last_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.projectName or "Unnamed Project"