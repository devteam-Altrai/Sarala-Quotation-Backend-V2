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
    po_reference = models.CharField(null=True, blank=True, max_length=100)
    part_status = models.CharField(null=True, blank=True, max_length=100)
    part_remark = models.CharField(null=True, blank=True, max_length=450)
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
    projectStatus = models.CharField(null=True, blank=True, max_length=100)
    ext_info = models.CharField(null=True, blank=True, max_length=300)

    # Automatically updated every time the record is saved
    last_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.projectName or "Unnamed Project"

class NumberEntry(models.Model):
    value = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.value)

class PoNumber(models.Model):
    projectName = models.CharField(null=True, blank=True, max_length=100)
    po_number = models.CharField(max_length=125)

class OrderStatus(models.Model):
    projectName = models.CharField(max_length=100, null=True, blank=True)
    quotationname = models.CharField(max_length=125, null=True, blank=True)
    order_serial = models.CharField(max_length=125, unique=True)
    po_number = models.CharField(max_length=125, null=True, blank=True)
    po_status = models.CharField(max_length=125, null=True, blank=True)
    dc_number = models.CharField(max_length=125, null=True, blank=True)
    dispatch_date = models.CharField(max_length=10, null=True, blank=True)
    tracking_number = models.CharField(max_length=125, null=True, blank=True)
    invoice_status = models.CharField(max_length=125, null=True, blank=True)
    invoice_number = models.CharField(max_length=125, null=True, blank=True)
    payment_status = models.CharField(max_length=125, null=True, blank=True)
    po_contact = models.CharField(max_length=125, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.projectName} - {self.order_serial}"